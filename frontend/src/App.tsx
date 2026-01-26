import { useState, useEffect, useRef } from 'react';
import ChatInterface from './components/ChatInterface';
import KnowledgeGraph from './components/KnowledgeGraph';
import AffinityChart from './components/AffinityChart';
import AffinityDashboard from './components/AffinityDashboard';
import { ContentRecommendation } from './components/ContentRecommendation';
import { ContentPreferenceSettings } from './components/ContentPreferenceSettings';
import { MemePreferenceSettings } from './components/MemePreferenceSettings';
import ProactiveNotification from './components/ProactiveNotification';
import ProactiveSettings from './components/ProactiveSettings';
import { api } from './services/api';
import type { GraphData, AffinityPoint } from './types';
import { MOCK_GRAPH_DATA_DAY_1 } from './constants';
import { Clock, Database, Heart, Newspaper, LayoutDashboard } from 'lucide-react';

export default function App() {
  const [currentDay, setCurrentDay] = useState<number>(30); 
  // Initial state can be empty if waiting for fetch, or mock for immediate demo
  const [graphData, setGraphData] = useState<GraphData>(MOCK_GRAPH_DATA_DAY_1);
  const [affinityData, setAffinityData] = useState<AffinityPoint[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<'graph' | 'content' | 'dashboard'>('graph');
  const [isProactiveSettingsOpen, setIsProactiveSettingsOpen] = useState(false);
  const hasLoadedRef = useRef(false);

  const fetchData = async () => {
    try {
      const [graph, affinity] = await Promise.all([
        api.getGraphData(currentDay),
        api.getAffinityHistory()
      ]);
      setGraphData(graph);
      setAffinityData(affinity);
    } catch (e) {
    }
  };

  useEffect(() => {
    let cancelled = false;
    const delayMs = hasLoadedRef.current ? 250 : 12000;
    hasLoadedRef.current = true;
    const timerId = window.setTimeout(async () => {
      if (cancelled) return;
      await fetchData();
    }, delayMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [currentDay]);

  const handleMemoryUpdate = () => {
    console.log("Memory committed! Refreshing graph...");
    fetchData();
  };

  return (
    <div className="flex h-screen w-full bg-gray-50 text-gray-800 font-sans selection:bg-blue-100 overflow-hidden">
      
      {/* LEFT: Chat Interface */}
      <div className={`flex flex-col h-full transition-all duration-300 ease-in-out ${isSidebarOpen ? 'w-full md:w-[400px] flex-shrink-0' : 'w-0 overflow-hidden opacity-0'} border-r border-gray-200 bg-white shadow-lg z-20`}>
        <div className="p-4 border-b border-gray-200 bg-white flex-shrink-0">
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">AI 陪伴助手</h1>
            <p className="text-xs text-gray-500 mt-1">记忆与情感系统 v6.0</p>
        </div>
        <div className="flex-grow p-4 bg-gray-50/50 min-h-0">
           <ChatInterface onMemoryUpdate={handleMemoryUpdate} />
        </div>
      </div>

      {/* RIGHT: Visualization Dashboard */}
      <div className={`flex flex-col flex-grow h-full bg-gray-50 transition-all duration-300 relative min-w-0`}>
        
        {/* Toggle Button for Layout */}
        <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="absolute left-4 top-4 z-50 p-2 bg-white rounded-md text-gray-500 hover:text-blue-600 shadow-md border border-gray-200 transition-colors"
            title={isSidebarOpen ? "折叠侧边栏" : "展开侧边栏"}
        >
            {isSidebarOpen ? '<<' : '>>'}
        </button>

        {/* Tab Navigation */}
        <div className="h-14 border-b border-gray-200 flex items-center px-8 gap-2 bg-white/80 backdrop-blur-md flex-shrink-0 z-10">
            <div className={`flex items-center gap-2 transition-all duration-300 ${isSidebarOpen ? 'ml-8' : 'ml-10'}`}>
              <button
                onClick={() => setActiveTab('graph')}
                className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${
                  activeTab === 'graph'
                    ? 'bg-blue-50 text-blue-600 font-medium'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Database size={16} />
                <span className="text-sm">记忆图谱</span>
              </button>
              <button
                onClick={() => setActiveTab('content')}
                className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${
                  activeTab === 'content'
                    ? 'bg-blue-50 text-blue-600 font-medium'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Newspaper size={16} />
                <span className="text-sm">内容推荐</span>
              </button>
              <button
                onClick={() => setActiveTab('dashboard')}
                className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${
                  activeTab === 'dashboard'
                    ? 'bg-blue-50 text-blue-600 font-medium'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <LayoutDashboard size={16} />
                <span className="text-sm">关系仪表盘</span>
              </button>
            </div>
        </div>

        {/* Content Area */}
        {activeTab === 'graph' ? (
          <>
            {/* Top Bar: Timeline Slider */}
            <div className="h-16 border-b border-gray-200 flex items-center px-8 gap-6 bg-white/80 backdrop-blur-md flex-shrink-0 z-10">
                <div className="flex items-center gap-2 text-gray-500 min-w-[100px]">
                    <Clock size={18} />
                    <span className="text-sm font-medium">时间轴</span>
                </div>
                <div className="flex-grow flex items-center gap-4 max-w-3xl">
                    <span className="text-xs text-gray-400">第 1 天</span>
                    <input 
                        type="range" 
                        min="1" 
                        max="90" 
                        value={currentDay}
                        onChange={(e) => setCurrentDay(parseInt(e.target.value))}
                        className="flex-grow h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600 hover:accent-blue-500 transition-all"
                    />
                    <span className="text-xs text-blue-600 font-mono font-bold bg-blue-50 px-2 py-1 rounded border border-blue-100 min-w-[60px] text-center">
                      Day {currentDay}
                    </span>
                </div>
            </div>

            {/* Main Vis Area */}
            <div className="flex-grow p-6 grid grid-rows-[3fr_2fr] gap-6 overflow-hidden min-h-0">
                
                {/* Upper: Graph */}
                <div className="flex flex-col gap-2 min-h-0">
                    <div className="flex items-center gap-2 text-gray-500 mb-1 px-1">
                        <Database size={16} />
                        <span className="text-xs uppercase tracking-wider font-semibold">记忆图谱可视化</span>
                    </div>
                    <div className="flex-grow relative min-h-0">
                        <KnowledgeGraph data={graphData} day={currentDay} />
                    </div>
                </div>

                {/* Lower: Affinity */}
                <div className="flex flex-col gap-2 min-h-0">
                    <div className="flex items-center gap-2 text-gray-500 mb-1 px-1">
                        <Heart size={16} />
                        <span className="text-xs uppercase tracking-wider font-semibold">情感亲密度状态</span>
                    </div>
                    <div className="flex-grow min-h-0">
                      <AffinityChart data={affinityData} currentDay={currentDay} />
                    </div>
                </div>

            </div>
          </>
        ) : activeTab === 'content' ? (
          /* Content Recommendation View */
          <div className="flex-grow p-6 overflow-auto">
            <div className="max-w-4xl mx-auto space-y-8">
              <ContentRecommendation />
              <ContentPreferenceSettings />
              <MemePreferenceSettings />
            </div>
          </div>
        ) : (
          /* Affinity Dashboard View */
          <AffinityDashboard affinityHistory={affinityData} currentDay={currentDay} onRefreshGraph={fetchData} />
        )}
      </div>

      {/* Proactive Message Notification */}
      <ProactiveNotification onOpenSettings={() => setIsProactiveSettingsOpen(true)} />

      {/* Proactive Settings Modal */}
      <ProactiveSettings 
        isOpen={isProactiveSettingsOpen} 
        onClose={() => setIsProactiveSettingsOpen(false)} 
      />
    </div>
  );
}
