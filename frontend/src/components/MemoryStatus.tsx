import React, { useEffect, useState } from 'react';
import { MemoryState } from '../types';
import { Trash2, Loader2, CheckCircle2 } from 'lucide-react';

interface MemoryStatusProps {
  state: MemoryState;
}

const MemoryStatus: React.FC<MemoryStatusProps> = ({ state }) => {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    // Reset visibility if state changes back to pending or something else
    if (state !== MemoryState.COMMITTED) {
      setVisible(true);
      return;
    }

    // If committed, start timer to fade out
    if (state === MemoryState.COMMITTED) {
      const timer = setTimeout(() => {
        setVisible(false);
      }, 3000); // 3 seconds delay
      return () => clearTimeout(timer);
    }
  }, [state]);

  if (!visible && state === MemoryState.COMMITTED) return null;

  switch (state) {
    case MemoryState.PENDING:
      return (
        <div className="flex items-center gap-1.5 text-[10px] text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200 shadow-sm animate-pulse" title="正在处理到短期记忆...">
          <Loader2 size={10} className="animate-spin" />
          <span className="font-medium">记忆中...</span>
        </div>
      );
    case MemoryState.COMMITTED:
      return (
        <div 
          className={`flex items-center gap-1.5 text-[10px] text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 shadow-sm transition-opacity duration-1000 ${visible ? 'opacity-100' : 'opacity-0'}`} 
          title="已存入知识图谱"
        >
          <CheckCircle2 size={10} />
          <span className="font-medium">已记住</span>
        </div>
      );
    case MemoryState.DELETED:
      return (
        <div className="flex items-center gap-1.5 text-[10px] text-red-500 bg-red-50 px-2 py-0.5 rounded-full border border-red-200 shadow-sm">
          <Trash2 size={10} />
          <span className="font-medium">已遗忘</span>
        </div>
      );
    default:
      return null;
  }
};

export default MemoryStatus;
