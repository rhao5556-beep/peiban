"""测试硅基流动 LLM API"""
import asyncio
import openai
from app.core.config import settings
from app.core.llm import normalize_openai_base_url

async def test_llm():
    client = openai.AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=normalize_openai_base_url(settings.OPENAI_API_BASE)
    )
    
    print(f"API Key set: {bool(settings.OPENAI_API_KEY)}")
    print(f"API Base: {normalize_openai_base_url(settings.OPENAI_API_BASE)}")
    print(f"Model: {settings.OPENAI_MODEL or 'deepseek-ai/DeepSeek-V3'}")
    print("\n开始测试流式调用...\n")
    
    try:
        response = await client.chat.completions.create(
            model=(settings.OPENAI_MODEL or "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "user", "content": "你好，请用一句话介绍你自己"}
            ],
            max_tokens=100,
            stream=True
        )
        
        full_text = ""
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                print(content, end="", flush=True)
                full_text += content
        
        print(f"\n\n完整回复: {full_text}")
        print(f"回复长度: {len(full_text)} 字符")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_llm())
