"""诊断 LLM API 调用问题"""
import asyncio
import sys
sys.path.insert(0, '.')

from openai import AsyncOpenAI
from app.core.config import settings

async def test_llm_api():
    """测试 LLM API 是否正常工作"""
    print("=" * 60)
    print("诊断 LLM API 调用")
    print("=" * 60)
    
    print(f"\nAPI Base: {settings.OPENAI_API_BASE}")
    print(f"API Key: {settings.OPENAI_API_KEY[:20]}...")
    
    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE
    )
    
    # 测试简单调用
    test_message = "你好"
    print(f"\n测试消息: {test_message}")
    print("-" * 40)
    
    try:
        response = await client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3",
            messages=[
                {"role": "system", "content": "你是一个友好的 AI 助手。"},
                {"role": "user", "content": test_message}
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        reply = response.choices[0].message.content
        print(f"\nLLM 回复: {reply}")
        print("\n✓ LLM API 调用成功")
        
    except Exception as e:
        print(f"\n✗ LLM API 调用失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_llm_api())
