import { useEffect, useRef, useState } from 'react';
import { Sender, MemoryState } from '../types';
import type { Message } from '../types';
import { api } from '../services/api';
import MemoryStatus from './MemoryStatus';
import { Send, Activity, Zap } from 'lucide-react';

interface ChatInterfaceProps {
  onMemoryUpdate: () => void; // Callback to trigger graph refresh
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ onMemoryUpdate }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      text: "你好，我已上线。今天感觉怎么样？",
      sender: Sender.AI,
      timestamp: Date.now(),
      memoryState: MemoryState.NONE
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const isProcessingRef = useRef(false); // 防止 StrictMode 双重调用
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleSend = async () => {
    if (!inputText.trim() || isStreaming) return;
    
    // 防止 StrictMode 双重调用
    if (isProcessingRef.current) {
      console.debug("Skipping duplicate handleSend call");
      return;
    }
    isProcessingRef.current = true;

    const userText = inputText;
    setInputText('');
    
    // 1. Add User Message
    const userMsg: Message = {
      id: Date.now().toString(),
      text: userText,
      sender: Sender.USER,
      timestamp: Date.now()
    };
    setMessages(prev => [...prev, userMsg]);

    // 2. Prepare Placeholder for AI Message
    const aiMsgId = (Date.now() + 1).toString();
    const initialAiMsg: Message = {
      id: aiMsgId,
      text: '',
      sender: Sender.AI,
      timestamp: Date.now(),
      memoryState: MemoryState.NONE,
      isTyping: true
    };
    setMessages(prev => [...prev, initialAiMsg]);
    setIsStreaming(true);

    try {
      // 3. Consume the Stream (Fast Path)
      const stream = api.sendMessageStream(userText);
      let fullText = '';
      let memoryPendingId: string | null = null;

      for await (const event of stream) {
        // Update the AI message in place
        if (event.type === 'text') {
          const newContent = event.content || '';
          fullText += newContent;
          setMessages(prev => prev.map(msg => 
            msg.id === aiMsgId ? { ...msg, text: fullText, isTyping: true } : msg
          ));
        } else if (event.type === 'memory_pending') {
          memoryPendingId = event.memory_id || null;
          setMessages(prev => prev.map(msg => 
            msg.id === aiMsgId ? { 
              ...msg, 
              memoryState: MemoryState.PENDING,
              memoryId: event.memory_id 
            } : msg
          ));
        } else if (event.type === 'done') {
          setMessages(prev => prev.map(msg => 
            msg.id === aiMsgId ? { ...msg, isTyping: false } : msg
          ));
        }
      }

      // 4. Trigger Polling if Memory is Pending (Slow Path / Fallback)
      if (memoryPendingId) {
          api.pollMemoryStatus(memoryPendingId, () => {
              // Update UI to Committed
              setMessages(prev => prev.map(msg => {
                  if (msg.id === aiMsgId) {
                      return { ...msg, memoryState: MemoryState.COMMITTED };
                  }
                  return msg;
              }));
              // Trigger Graph Refresh
              onMemoryUpdate();
          });
      }

    } catch (error) {
      console.error("Stream failed", error);
      setMessages(prev => prev.map(msg => 
        msg.id === aiMsgId ? { ...msg, text: "连接异常。", isTyping: false } : msg
      ));
    } finally {
      setIsStreaming(false);
      isProcessingRef.current = false; // 重置处理标志
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-white border-b border-gray-100 flex justify-between items-center flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]`}></div>
          <span className="font-semibold text-gray-800">系统就绪</span>
        </div>
        <div className="text-xs text-gray-500 flex items-center gap-1">
          {isStreaming ? <Activity size={14} className="animate-pulse text-amber-500" /> : <Zap size={14} />}
          {isStreaming ? '生成中...' : '空闲'}
        </div>
      </div>

      {/* Messages Area - KEY FIX: min-h-0 allows nested flex scroll to work properly */}
      <div className="flex-grow min-h-0 overflow-y-auto p-4 space-y-6 bg-gray-50/50">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex flex-col ${msg.sender === Sender.USER ? 'items-end' : 'items-start'}`}>
            <div 
              className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm ${
                msg.sender === Sender.USER 
                  ? 'bg-blue-600 text-white rounded-br-none shadow-blue-500/20' 
                  : 'bg-white text-gray-700 rounded-bl-none border border-gray-200'
              }`}
            >
              {msg.text}
              {msg.isTyping && <span className="inline-block w-1.5 h-3 ml-1 bg-gray-400 animate-pulse align-middle"></span>}
            </div>
            
            {/* Memory State Indicator */}
            {msg.sender === Sender.AI && msg.memoryState && msg.memoryState !== MemoryState.NONE && (
              <div className="mt-1 ml-1 animate-in fade-in duration-300 h-5">
                <MemoryStatus state={msg.memoryState} />
              </div>
            )}
            
            <span className="text-[10px] text-gray-400 mt-1 mx-1">
              {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-gray-100 flex-shrink-0">
        <div className="relative flex items-end gap-2">
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="与 AI 对话 (提及 '咖啡' 可触发记忆)..."
            className="flex-grow bg-gray-50 text-gray-800 rounded-xl border border-gray-200 p-3 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none h-12 max-h-24 scrollbar-hide text-sm transition-all"
          />
          <button 
            onClick={handleSend}
            disabled={!inputText.trim() || isStreaming}
            className="flex-shrink-0 p-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm h-12 w-12 flex items-center justify-center"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
