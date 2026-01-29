"""记忆端点 - GDPR 合规删除"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import hashlib
import hmac
import json

from app.core.security import get_current_user
from app.core.database import get_db
from app.core.config import settings
from app.models.memory import Memory, DeletionAudit
from app.worker.tasks.deletion import delete_user_data

router = APIRouter()


class MemoryResponse(BaseModel):
    """记忆响应"""
    id: str
    content: str
    valence: Optional[float] = None
    status: str
    created_at: datetime
    committed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class MemorySearchRequest(BaseModel):
    """记忆搜索请求"""
    query: str
    top_k: int = 10


class MemorySearchResult(BaseModel):
    """记忆搜索结果"""
    id: str
    content: str
    cosine_sim: float
    edge_weight: float
    affinity_bonus: float
    recency_score: float
    final_score: float


class DeleteRequest(BaseModel):
    """删除请求"""
    memory_ids: Optional[List[str]] = None
    delete_all: bool = False


class DeletionAuditResponse(BaseModel):
    """删除审计响应"""
    audit_id: str
    user_id: str
    deletion_type: str
    affected_count: int
    requested_at: datetime
    status: str
    audit_hash: str
    signature: Optional[str] = None
    
    class Config:
        from_attributes = True


class AuditVerifyRequest(BaseModel):
    """审计验证请求"""
    audit_id: str
    signature: str


class AuditVerifyResponse(BaseModel):
    """审计验证响应"""
    audit_id: str
    valid: bool
    message: str
    verified_at: Optional[datetime] = None


def generate_audit_hash(data: dict) -> str:
    """生成审计数据的 HMAC 签名"""
    message = json.dumps(data, sort_keys=True, default=str).encode()
    secret = settings.JWT_SECRET.encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_audit_signature(audit_data: dict, signature: str) -> bool:
    """验证审计签名"""
    expected_hash = generate_audit_hash(audit_data)
    return hmac.compare_digest(expected_hash, signature)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取单条记忆详情
    
    用于前端轮询检查记忆状态 (Pending -> Committed)
    """
    user_id = current_user["user_id"]
    
    try:
        mem_uuid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memory_id format")
    
    query = select(Memory).where(
        Memory.id == mem_uuid,
        Memory.user_id == uuid.UUID(user_id)
    )
    result = await db.execute(query)
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return MemoryResponse(
        id=str(memory.id),
        content=memory.content,
        valence=memory.valence,
        status=memory.status,
        created_at=memory.created_at,
        committed_at=memory.committed_at
    )


@router.get("/", response_model=List[MemoryResponse])
async def list_memories(
    status: Optional[str] = Query(None, description="Filter by status: pending, committed, deleted"),
    limit: int = Query(50, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户记忆列表（不返回已删除记录）"""
    user_id = current_user["user_id"]
    
    query = select(Memory).where(Memory.user_id == uuid.UUID(user_id))
    
    # 默认不返回已删除记录（GDPR Property 7）
    if status:
        query = query.where(Memory.status == status)
    else:
        query = query.where(Memory.status != "deleted")
    
    query = query.limit(limit).order_by(Memory.created_at.desc())
    
    result = await db.execute(query)
    memories = result.scalars().all()
    
    return [
        MemoryResponse(
            id=str(m.id),
            content=m.content,
            valence=m.valence,
            status=m.status,
            created_at=m.created_at,
            committed_at=m.committed_at
        )
        for m in memories
    ]


@router.post("/search", response_model=List[MemorySearchResult])
async def search_memories(
    request: MemorySearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    混合检索记忆
    
    使用 Vector + Graph 混合检索，返回带完整分数分解的结果
    Property 7: 已删除记录不会出现在检索结果中
    """
    user_id = current_user["user_id"]
    
    # 只检索非删除状态的记忆
    from app.services.retrieval_service import RetrievalService
    from app.services.affinity_service import AffinityService
    
    retrieval_service = RetrievalService()
    affinity_service = AffinityService(db)
    
    # 获取当前好感度
    affinity = await affinity_service.get_affinity(user_id)
    
    # 混合检索（内部过滤已删除记录）
    results = await retrieval_service.hybrid_retrieve(
        user_id=user_id,
        query=request.query,
        affinity_score=affinity.score if affinity else 0.0,
        top_k=request.top_k
    )
    
    return [
        MemorySearchResult(
            id=r.id,
            content=r.content,
            cosine_sim=r.cosine_sim,
            edge_weight=r.edge_weight,
            affinity_bonus=r.affinity_bonus,
            recency_score=r.recency_score,
            final_score=r.final_score
        )
        for r in results
    ]


@router.delete("/", response_model=DeletionAuditResponse)
async def delete_memories(
    request: DeleteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除记忆（GDPR 合规）
    
    - 逻辑删除：即时标记 status = deleted
    - 物理删除：72h SLA，异步执行
    - 返回删除审计证明（带 HMAC 签名）
    
    Property 7: 删除后不可检索
    Property 8: 物理删除 72h SLA
    Property 13: 删除可验证性
    """
    user_id = current_user["user_id"]
    user_uuid = uuid.UUID(user_id)
    
    if not request.memory_ids and not request.delete_all:
        raise HTTPException(
            status_code=400,
            detail="Must specify memory_ids or set delete_all=true"
        )
    
    # 1. 执行逻辑删除
    affected_count = 0
    affected_ids = []
    
    if request.delete_all:
        # 删除用户所有记忆
        query = select(Memory).where(
            Memory.user_id == user_uuid,
            Memory.status != "deleted"
        )
        result = await db.execute(query)
        memories = result.scalars().all()
        
        for memory in memories:
            memory.status = "deleted"
            affected_ids.append(str(memory.id))
            affected_count += 1
    else:
        # 删除指定记忆
        for memory_id in request.memory_ids:
            try:
                mem_uuid = uuid.UUID(memory_id)
            except ValueError:
                continue
                
            query = select(Memory).where(
                Memory.id == mem_uuid,
                Memory.user_id == user_uuid,
                Memory.status != "deleted"
            )
            result = await db.execute(query)
            memory = result.scalar_one_or_none()
            
            if memory:
                memory.status = "deleted"
                affected_ids.append(str(memory.id))
                affected_count += 1
    
    # 2. 创建审计记录
    audit_id = uuid.uuid4()
    deletion_type = "full" if request.delete_all else "selective"
    
    affected_records = {
        "memory_ids": affected_ids,
        "count": affected_count,
        "deletion_type": deletion_type
    }
    
    # 生成 HMAC 签名
    audit_data = {
        "audit_id": str(audit_id),
        "user_id": user_id,
        "deletion_type": deletion_type,
        "affected_records": affected_records,
        "requested_at": datetime.utcnow().isoformat()
    }
    audit_hash = generate_audit_hash(audit_data)
    
    # 保存审计记录
    audit = DeletionAudit(
        id=audit_id,
        user_id=user_uuid,
        deletion_type=deletion_type,
        affected_records=affected_records,
        audit_hash=audit_hash,
        status="pending"
    )
    db.add(audit)
    
    await db.commit()
    
    # 3. 触发异步物理删除任务
    delete_user_data.delay(user_id, deletion_type)
    
    return DeletionAuditResponse(
        audit_id=str(audit_id),
        user_id=user_id,
        deletion_type=deletion_type,
        affected_count=affected_count,
        requested_at=audit.requested_at,
        status="pending",
        audit_hash=audit_hash
    )


@router.get("/audit/{audit_id}", response_model=DeletionAuditResponse)
async def get_deletion_audit(
    audit_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取删除审计详情"""
    user_id = current_user["user_id"]
    
    try:
        audit_uuid = uuid.UUID(audit_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid audit_id format")
    
    query = select(DeletionAudit).where(
        DeletionAudit.id == audit_uuid,
        DeletionAudit.user_id == uuid.UUID(user_id)
    )
    result = await db.execute(query)
    audit = result.scalar_one_or_none()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit record not found")
    
    return DeletionAuditResponse(
        audit_id=str(audit.id),
        user_id=str(audit.user_id),
        deletion_type=audit.deletion_type,
        affected_count=audit.affected_records.get("count", 0),
        requested_at=audit.requested_at,
        status=audit.status,
        audit_hash=audit.audit_hash,
        signature=audit.signature
    )


@router.post("/audit/verify", response_model=AuditVerifyResponse)
async def verify_deletion_audit(
    request: AuditVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    验证删除审计签名
    
    用于证明删除已执行（Property 13: 删除可验证性）
    """
    user_id = current_user["user_id"]
    
    try:
        audit_uuid = uuid.UUID(request.audit_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid audit_id format")
    
    # 获取审计记录
    query = select(DeletionAudit).where(
        DeletionAudit.id == audit_uuid,
        DeletionAudit.user_id == uuid.UUID(user_id)
    )
    result = await db.execute(query)
    audit = result.scalar_one_or_none()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit record not found")
    
    # 重建审计数据并验证签名
    audit_data = {
        "audit_id": str(audit.id),
        "user_id": str(audit.user_id),
        "deletion_type": audit.deletion_type,
        "affected_records": audit.affected_records,
        "requested_at": audit.requested_at.isoformat()
    }
    
    is_valid = verify_audit_signature(audit_data, request.signature)
    
    if is_valid:
        # 验证删除确实已执行
        memory_ids = audit.affected_records.get("memory_ids", [])
        if memory_ids:
            check_query = select(Memory).where(
                Memory.id.in_([uuid.UUID(mid) for mid in memory_ids]),
                Memory.status != "deleted"
            )
            check_result = await db.execute(check_query)
            undeleted = check_result.scalars().all()
            
            if undeleted:
                return AuditVerifyResponse(
                    audit_id=request.audit_id,
                    valid=False,
                    message=f"Signature valid but {len(undeleted)} records not yet deleted"
                )
    
    return AuditVerifyResponse(
        audit_id=request.audit_id,
        valid=is_valid,
        message="Deletion verified successfully" if is_valid else "Invalid signature",
        verified_at=datetime.utcnow() if is_valid else None
    )
