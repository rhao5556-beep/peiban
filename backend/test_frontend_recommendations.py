"""
使用 Selenium 自动测试前端推荐功能
"""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

def test_recommendations():
    print("=" * 60)
    print("开始测试前端推荐功能...")
    print("=" * 60)
    
    # 配置 Chrome 选项
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # 无头模式
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    driver = None
    
    try:
        # 启动浏览器
        print("\n🌐 启动浏览器...")
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        
        # 访问前端页面
        print("📱 访问前端页面: http://localhost:5173")
        driver.get("http://localhost:5173")
        
        # 等待页面加载
        time.sleep(3)
        
        # 切换到内容推荐标签页
        print("\n🔄 切换到内容推荐标签...")
        try:
            content_tab = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '内容推荐')]"))
            )
            content_tab.click()
            time.sleep(2)
        except Exception as e:
            print(f"⚠️  未找到内容推荐标签，可能已经在该页面: {e}")
        
        # 检查是否有推荐内容
        print("\n🔍 检查推荐内容...")
        
        # 等待推荐内容加载
        time.sleep(3)
        
        # 查找推荐卡片
        try:
            recommendations = driver.find_elements(By.CSS_SELECTOR, ".bg-white.border.border-gray-200.rounded-lg")
            
            if recommendations:
                print(f"\n✅ 成功！找到 {len(recommendations)} 条推荐")
                
                # 提取推荐标题
                for i, rec in enumerate(recommendations[:3], 1):
                    try:
                        title_element = rec.find_element(By.CSS_SELECTOR, "h3")
                        title = title_element.text
                        print(f"\n{i}. {title}")
                    except Exception as e:
                        print(f"\n{i}. (无法提取标题: {e})")
                
                print("\n" + "=" * 60)
                print("✅ 测试通过！前端成功显示推荐内容")
                print("=" * 60)
                return True
            else:
                # 检查是否显示"暂无推荐内容"
                page_source = driver.page_source
                
                if "暂无推荐内容" in page_source:
                    print("\n⚠️  页面显示'暂无推荐内容'")
                    print("   可能原因：")
                    print("   1. 用户未启用推荐")
                    print("   2. 今日没有内容")
                    print("   3. 推荐生成失败")
                elif "系统正在为您准备推荐内容" in page_source:
                    print("\n✅ 页面显示正确的提示信息")
                    print("   '系统正在为您准备推荐内容，请稍后查看'")
                else:
                    print("\n❌ 未找到推荐内容或提示信息")
                    print(f"   页面内容片段: {page_source[:500]}")
                
                return False
                
        except Exception as e:
            print(f"\n❌ 查找推荐内容时出错: {e}")
            print(f"   页面标题: {driver.title}")
            print(f"   当前 URL: {driver.current_url}")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if driver:
            driver.quit()
            print("\n🔚 浏览器已关闭")


if __name__ == "__main__":
    success = test_recommendations()
    exit(0 if success else 1)
