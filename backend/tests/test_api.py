"""API 端点测试"""
import uuid
import pytest
from httpx import AsyncClient


class TestHealthCheck:
    """健康检查测试"""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """测试健康检查端点"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestAuth:
    """认证测试"""
    
    @pytest.mark.asyncio
    async def test_get_token(self, client: AsyncClient):
        """测试获取 Token"""
        response = await client.post("/api/v1/auth/token", json={})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user_id" in data
    
    @pytest.mark.asyncio
    async def test_get_token_with_user_id(self, client: AsyncClient):
        """测试使用指定用户 ID 获取 Token"""
        response = await client.post(
            "/api/v1/auth/token",
            json={"user_id": "custom-user-id"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(uuid.uuid5(uuid.NAMESPACE_URL, "custom-user-id"))


class TestConversation:
    """对话测试"""
    
    @pytest.mark.asyncio
    async def test_send_message(self, client: AsyncClient, auth_headers: dict):
        """测试发送消息"""
        response = await client.post(
            "/api/v1/conversation/message",
            json={"message": "你好"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "session_id" in data
        assert "emotion" in data
        assert "affinity" in data
    
    @pytest.mark.asyncio
    async def test_send_message_unauthorized(self, client: AsyncClient):
        """测试未授权发送消息"""
        response = await client.post(
            "/api/v1/conversation/message",
            json={"message": "你好"}
        )
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_create_session(self, client: AsyncClient, auth_headers: dict):
        """测试创建会话"""
        response = await client.post(
            "/api/v1/conversation/session",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "user_id" in data


class TestAffinity:
    """好感度测试"""
    
    @pytest.mark.asyncio
    async def test_get_affinity(self, client: AsyncClient, auth_headers: dict):
        """测试获取好感度"""
        response = await client.get(
            "/api/v1/affinity/",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert "state" in data
        assert -1 <= data["score"] <= 1
    
    @pytest.mark.asyncio
    async def test_get_state_mapping(self, client: AsyncClient, auth_headers: dict):
        """测试获取状态映射"""
        response = await client.get(
            "/api/v1/affinity/state-mapping",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "stranger" in data
        assert "best_friend" in data


class TestMemory:
    """记忆测试"""
    
    @pytest.mark.asyncio
    async def test_list_memories(self, client: AsyncClient, auth_headers: dict):
        """测试获取记忆列表"""
        response = await client.get(
            "/api/v1/memory/",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    @pytest.mark.asyncio
    async def test_search_memories(self, client: AsyncClient, auth_headers: dict):
        """测试搜索记忆"""
        response = await client.post(
            "/api/v1/memory/search",
            json={"query": "家人", "top_k": 10},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestGraph:
    """图谱测试"""
    
    @pytest.mark.asyncio
    async def test_get_graph(self, client: AsyncClient, auth_headers: dict):
        """测试获取图谱"""
        response = await client.get(
            "/api/v1/graph/",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
    
    @pytest.mark.asyncio
    async def test_get_graph_stats(self, client: AsyncClient, auth_headers: dict):
        """测试获取图谱统计"""
        response = await client.get(
            "/api/v1/graph/stats",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_nodes" in data
        assert "total_edges" in data
