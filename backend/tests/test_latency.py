"""
延迟分析：找出对话生成慢的原因
"""
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def analyze_latency():
    """分析各阶段延迟"""
    from pymilvus import connections
    from app.core.config import settings
    
    connections.connect(alias="default", host=settings.MILVUS_HOST, port=settings.MILVUS_PORT)
    
    from app.services.conversation_service import ConversationService, ConversationMode
    from app.services.affinity_service import AffinityService
    from app.services.retrieval_service import RetrievalService, EmbeddingService
    from app.services.graph_service import GraphService
    from app.core.database import get_neo4j_driver, get_milvus_collection
    
    neo4j_driver = get_neo4j_driver()
    milvus_collection = get_milvus_collection()
    
    graph_service = GraphService(neo4j_driver=neo4j_driver)
    retrieval_service = RetrievalService(milvus_client=milvus_collection, graph_service=graph_service)
    affinity_service = AffinityService()
    embedding_service = EmbeddingService()
    
    question = "二丫来自哪里？"
    
    print("\n" + "="*60)
    print("延迟分析")
    print("="*60)
    
    timings = {}
    
    # 1. Embedding 生成
    t0 = time.time()
    embedding = await embedding_service.encode(question)
    timings["1. Embedding"] = (time.time() - t0) * 1000
    
    # 2. Milvus 向量搜索
    t0 = time.time()
    from app.services.retrieval_service import RetrievalResult
    vector_results = await retrieval_service.hybrid_retrieve(TEST_USER_ID, question, 0.5)
    timings["2. Milvus 向量搜索"] = (time.time() - t0) * 1000
    
    # 3. 图谱事实检索（包含 LLM 实体抽取）
    t0 = time.time()
    entity_facts = await retrieval_service.retrieve_entity_facts(TEST_USER_ID, question, graph_service)
    timings["3. 图谱事实检索 (含LLM实体抽取)"] = (time.time() - t0) * 1000
    
    # 4. Affinity 获取
    t0 = time.time()
    affinity = await affinity_service.get_affinity(TEST_USER_ID)
    timings["4. Affinity 获取"] = (time.time() - t0) * 1000
    
    # 5. LLM 回复生成
    import openai
    llm_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_API_BASE)
    
    t0 = time.time()
    response = await llm_client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V3",
        messages=[
            {"role": "system", "content": "你是一个情感陪伴 AI"},
            {"role": "user", "content": question}
        ],
        max_tokens=200,
        stream=False
    )
    timings["5. LLM 回复生成"] = (time.time() - t0) * 1000
    
    # 打印结果
    print("\n各阶段耗时:")
    total = 0
    for stage, ms in timings.items():
        print(f"  {stage}: {ms:.0f}ms")
        total += ms
    
    print(f"\n  总计: {total:.0f}ms")
    
    # 分析瓶颈
    print("\n瓶颈分析:")
    sorted_timings = sorted(timings.items(), key=lambda x: x[1], reverse=True)
    for stage, ms in sorted_timings[:3]:
        pct = ms / total * 100
        print(f"  {stage}: {ms:.0f}ms ({pct:.1f}%)")


if __name__ == "__main__":
    asyncio.run(analyze_latency())
