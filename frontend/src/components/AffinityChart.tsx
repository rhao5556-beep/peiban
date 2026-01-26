import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import type { AffinityPoint } from '../types';
import { Heart, User, Users, Star } from 'lucide-react';

interface AffinityChartProps {
  data: AffinityPoint[];
  currentDay: number;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const point = payload[0].payload;
    return (
      <div className="bg-white border border-gray-200 p-2 rounded shadow-xl text-xs z-50">
        <p className="font-bold text-gray-800">{point.timestamp}</p>
        <p className="text-purple-600">亲密度: {point.value}%</p>
        {point.event && (
          <p className="text-gray-500 mt-1 italic">"{point.event}"</p>
        )}
      </div>
    );
  }
  return null;
};

// Helper to determine relationship status
const getStatus = (value: number) => {
  if (value < 20) return { text: '陌生人', color: 'text-gray-500', icon: User, desc: '尚未建立深层连接' };
  if (value < 50) return { text: '熟人', color: 'text-blue-500', icon: Users, desc: '开始了解彼此的喜好' };
  if (value < 80) return { text: '朋友', color: 'text-purple-500', icon: Heart, desc: '建立了稳固的信任' };
  return { text: '知己', color: 'text-pink-500', icon: Star, desc: '心意相通，无可替代' };
};

const AffinityChart: React.FC<AffinityChartProps> = ({ data, currentDay }) => {
  const visibleData = data.filter(d => {
    const matches = d.timestamp.match(/\d+/);
    const dayNum = matches ? parseInt(matches[0]) : 0;
    return dayNum <= currentDay;
  });

  const currentValue = visibleData.length > 0 ? visibleData[visibleData.length - 1].value : 0;
  const status = getStatus(currentValue);
  const StatusIcon = status.icon;

  return (
    <div className="w-full h-full min-h-[220px] flex flex-col bg-white rounded-xl border border-gray-200 p-5 shadow-lg relative overflow-hidden">
      
      {/* 1. Header & Status Panel */}
      <div className="flex justify-between items-start mb-4 flex-shrink-0">
        <div>
          <h3 className="text-xs font-semibold text-gray-400 tracking-wider uppercase flex items-center gap-1.5">
            <Heart size={14} className="text-gray-400" />
            情感亲密度
          </h3>
          <div className="mt-2 flex items-baseline gap-2">
            <span className={`text-2xl font-bold ${status.color}`}>{status.text}</span>
            <span className="text-3xl font-light text-gray-800">{currentValue}%</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">{status.desc}</p>
        </div>
        <div className={`p-3 rounded-full bg-gray-50 ${status.color}`}>
          <StatusIcon size={24} />
        </div>
      </div>

      {/* 2. Progress Bar */}
      <div className="w-full h-2 bg-gray-100 rounded-full mb-6 overflow-hidden flex-shrink-0">
        <div 
          className="h-full bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500 transition-all duration-1000 ease-out"
          style={{ width: `${currentValue}%` }}
        />
      </div>

      {/* 3. Mini Chart */}
      <div className="flex-grow w-full min-h-0 relative">
        {visibleData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={visibleData} margin={{ top: 5, right: 5, bottom: 5, left: -25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
              <XAxis dataKey="timestamp" hide />
              <YAxis domain={[0, 100]} hide />
              <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#cbd5e1', strokeWidth: 1 }} />
              <Line 
                type="monotone" 
                dataKey="value" 
                stroke="#9333ea" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0, fill: '#9333ea' }}
                animationDuration={1500}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="w-full h-full flex items-center justify-center text-xs text-gray-400 italic">
            暂无历史数据
          </div>
        )}
      </div>
    </div>
  );
};

export default AffinityChart;