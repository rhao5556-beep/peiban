import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import type { GraphData } from '../types';
import { Download, Share2, RefreshCw, FolderOpen } from 'lucide-react';

interface KnowledgeGraphProps {
  data: GraphData;
  day: number;
}

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ data, day }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [, setLayoutReady] = useState(false);

  // 6.1.1 Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize only if we have a container, but we handle empty data in render now
    cyRef.current = cytoscape({
      container: containerRef.current,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': '#3b82f6', // blue-500
            'label': 'data(label)',
            'color': '#1f2937', // gray-800 (Dark text for light bg)
            'font-size': '12px',
            'text-valign': 'center',
            'text-halign': 'center',
            'width': 'mapData(weight, 0, 20, 20, 60)',
            'height': 'mapData(weight, 0, 20, 20, 60)',
            'text-outline-color': '#fff',
            'text-outline-width': 2,
            'border-width': 2,
            'border-color': '#60a5fa', // blue-400
            'font-weight': 'bold'
          }
        },
        {
          selector: 'node[type="event"]',
          style: {
            'background-color': '#ef4444', // red-500
            'shape': 'diamond',
            'border-color': '#f87171'
          }
        },
        {
          selector: 'node[type="concept"]',
          style: {
            'background-color': '#10b981', // green-500
            'shape': 'round-rectangle',
            'border-color': '#34d399'
          }
        },
        {
          selector: 'edge',
          style: {
            'width': 'mapData(weight, 0, 1, 1, 6)', // 根据权重调整边的粗细
            'line-color': '#9ca3af', // gray-400
            'target-arrow-color': '#9ca3af',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '10px',
            'color': '#6b7280', // gray-500
            'text-rotation': 'autorotate',
            'text-background-color': '#f3f4f6', // gray-100
            'text-background-opacity': 1,
            'text-background-padding': '2px',
            'opacity': 'mapData(weight, 0, 1, 0.3, 1)' // 根据权重调整透明度
          }
        }
      ],
      layout: { name: 'grid' },
      wheelSensitivity: 0.2,
    });

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
      }
    };
  }, []);

  // 6.1.2 Update Data & Layout on Change
  useEffect(() => {
    if (!cyRef.current) return;
    // Skip if no data
    if (!data || !data.nodes || data.nodes.length === 0) return;

    const cy = cyRef.current;
    
    // 创建节点 ID 集合用于验证边
    const nodeIds = new Set(data.nodes.map(n => n.id));
    
    // Batch update to prevent jitter
    cy.batch(() => {
      cy.elements().remove();
      
      const cyNodes = data.nodes.map(n => ({
        data: { 
          id: n.id, 
          label: n.label, 
          type: n.type, 
          weight: n.weight || 10,
          // 保存所有原始属性用于 tooltip
          ...n
        }
      }));
      
      // 过滤掉引用不存在节点的边
      const validEdges = data.edges.filter(e => {
        const sourceExists = nodeIds.has(e.source);
        const targetExists = nodeIds.has(e.target);
        if (!sourceExists || !targetExists) {
          console.warn(`Skipping edge ${e.id}: source=${e.source}(${sourceExists}) target=${e.target}(${targetExists})`);
          return false;
        }
        return true;
      });
      
      const cyEdges = validEdges.map(e => ({
        data: { 
          id: e.id, 
          source: e.source, 
          target: e.target, 
          label: e.label,
          weight: e.weight || 1,
          // 保存所有原始属性用于 tooltip
          ...e
        }
      }));

      cy.add([...cyNodes, ...cyEdges]);
    });

    // Run layout with animation
    const layout = cy.layout({
      name: 'cose',
      animate: true,
      animationDuration: 800,
      fit: true,
      padding: 30,
      randomize: false, 
      componentSpacing: 100,
      nodeRepulsion: (node: any) => 400000,
      edgeElasticity: (edge: any) => 100,
      nestingFactor: 5,
    } as any);

    layout.run();
    setLayoutReady(true);

  }, [data]);

  // 6.1.2.1 Add Tooltip on Hover
  useEffect(() => {
    if (!cyRef.current) return;
    const cy = cyRef.current;

    // 创建 tooltip 元素
    let tooltip: HTMLDivElement | null = null;

    const formatValue = (value: any): string => {
      if (value === null || value === undefined) return 'N/A';
      if (typeof value === 'number') return value.toFixed(3);
      if (typeof value === 'boolean') return value ? 'true' : 'false';
      if (Array.isArray(value)) return `[${value.length} items]`;
      if (typeof value === 'object') return JSON.stringify(value);
      return String(value);
    };

    const showTooltip = (evt: any) => {
      const target = evt.target;
      const data = target.data();
      
      // 移除旧的 tooltip
      if (tooltip) {
        tooltip.remove();
      }

      // 创建新的 tooltip
      tooltip = document.createElement('div');
      tooltip.style.position = 'fixed';
      tooltip.style.backgroundColor = 'rgba(0, 0, 0, 0.9)';
      tooltip.style.color = 'white';
      tooltip.style.padding = '10px 14px';
      tooltip.style.borderRadius = '8px';
      tooltip.style.fontSize = '11px';
      tooltip.style.lineHeight = '1.6';
      tooltip.style.pointerEvents = 'none';
      tooltip.style.zIndex = '10000';
      tooltip.style.maxWidth = '350px';
      tooltip.style.boxShadow = '0 4px 12px rgba(0,0,0,0.4)';
      tooltip.style.border = '1px solid rgba(255,255,255,0.1)';
      tooltip.style.fontFamily = 'monospace';

      // 构建 tooltip 内容
      let content = '';
      if (target.isNode()) {
        content = `<div style="font-weight: bold; margin-bottom: 6px; color: #60a5fa; font-size: 12px; border-bottom: 1px solid rgba(96, 165, 250, 0.3); padding-bottom: 4px;">📍 节点信息</div>`;
        
        // 按优先级排序属性
        const priorityKeys = ['label', 'name', 'type', 'mention_count', 'weight', 'first_mentioned_at', 'last_mentioned_at'];
        const allKeys = Object.keys(data);
        const sortedKeys = [
          ...priorityKeys.filter(k => allKeys.includes(k)),
          ...allKeys.filter(k => !priorityKeys.includes(k) && k !== 'id')
        ];
        
        sortedKeys.forEach(key => {
          const value = data[key];
          const displayValue = formatValue(value);
          content += `<div style="margin: 3px 0;"><span style="color: #9ca3af; font-weight: 600;">${key}:</span> <span style="color: #e5e7eb;">${displayValue}</span></div>`;
        });
      } else if (target.isEdge()) {
        content = `<div style="font-weight: bold; margin-bottom: 6px; color: #34d399; font-size: 12px; border-bottom: 1px solid rgba(52, 211, 153, 0.3); padding-bottom: 4px;">🔗 关系信息</div>`;
        
        // 按优先级排序属性
        const priorityKeys = ['label', 'relation_type', 'weight', 'current_weight', 'decay_rate', 'created_at', 'updated_at'];
        const allKeys = Object.keys(data);
        const sortedKeys = [
          ...priorityKeys.filter(k => allKeys.includes(k)),
          ...allKeys.filter(k => !priorityKeys.includes(k) && k !== 'id' && k !== 'source' && k !== 'target')
        ];
        
        sortedKeys.forEach(key => {
          const value = data[key];
          const displayValue = formatValue(value);
          content += `<div style="margin: 3px 0;"><span style="color: #9ca3af; font-weight: 600;">${key}:</span> <span style="color: #e5e7eb;">${displayValue}</span></div>`;
        });
      }

      tooltip.innerHTML = content;
      document.body.appendChild(tooltip);

      // 更新 tooltip 位置 - 使用 fixed 定位，相对于视口
      const updatePosition = (e: any) => {
        if (tooltip && containerRef.current) {
          const containerRect = containerRef.current.getBoundingClientRect();
          const renderedPos = e.renderedPosition || e.target.renderedPosition();
          
          // 计算相对于视口的位置
          const x = containerRect.left + renderedPos.x;
          const y = containerRect.top + renderedPos.y;
          
          // 偏移量更小，更靠近节点/边
          const offsetX = 15;
          const offsetY = -10;
          
          // 获取 tooltip 尺寸
          const tooltipRect = tooltip.getBoundingClientRect();
          
          // 计算最终位置，避免超出视口
          let finalX = x + offsetX;
          let finalY = y + offsetY;
          
          // 右边界检查
          if (finalX + tooltipRect.width > window.innerWidth - 10) {
            finalX = x - tooltipRect.width - offsetX;
          }
          
          // 下边界检查
          if (finalY + tooltipRect.height > window.innerHeight - 10) {
            finalY = y - tooltipRect.height - offsetY;
          }
          
          // 上边界检查
          if (finalY < 10) {
            finalY = 10;
          }
          
          // 左边界检查
          if (finalX < 10) {
            finalX = 10;
          }
          
          tooltip.style.left = `${finalX}px`;
          tooltip.style.top = `${finalY}px`;
        }
      };
      updatePosition(evt);
    };

    const hideTooltip = () => {
      if (tooltip) {
        tooltip.remove();
        tooltip = null;
      }
    };

    // 绑定事件
    cy.on('mouseover', 'node, edge', showTooltip);
    cy.on('mouseout', 'node, edge', hideTooltip);
    cy.on('drag', 'node', hideTooltip);
    cy.on('pan zoom', hideTooltip);

    // 清理函数
    return () => {
      cy.off('mouseover', 'node, edge', showTooltip);
      cy.off('mouseout', 'node, edge', hideTooltip);
      cy.off('drag', 'node', hideTooltip);
      cy.off('pan zoom', hideTooltip);
      if (tooltip) {
        tooltip.remove();
      }
    };
  }, [data]);

  // 6.1.3 Export Functionality
  const handleExport = (format: 'png' | 'json') => {
    if (!cyRef.current) return;
    
    if (format === 'png') {
      const png64 = cyRef.current.png({ full: true, bg: '#ffffff' }); // White bg
      const link = document.createElement('a');
      link.download = `graph-day-${day}.png`;
      link.href = png64;
      link.click();
    } else {
      const json = cyRef.current.json();
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(json));
      const link = document.createElement('a');
      link.download = `graph-day-${day}.json`;
      link.href = dataStr;
      link.click();
    }
  };

  const handleFit = () => {
    cyRef.current?.fit();
  };

  const hasData = data && data.nodes && data.nodes.length > 0;

  return (
    <div className="flex flex-col h-full w-full bg-white rounded-xl overflow-hidden border border-gray-200 shadow-lg relative group">
      {/* Toolbar - Only show if has data */}
      {hasData && (
        <div className="absolute top-4 right-4 z-10 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
          <button onClick={handleFit} className="p-2 bg-white hover:bg-gray-100 text-gray-700 rounded-lg shadow border border-gray-200" title="适应视图">
            <RefreshCw size={16} />
          </button>
          <button onClick={() => handleExport('png')} className="p-2 bg-white hover:bg-gray-100 text-gray-700 rounded-lg shadow border border-gray-200" title="导出 PNG">
            <Share2 size={16} />
          </button>
          <button onClick={() => handleExport('json')} className="p-2 bg-white hover:bg-gray-100 text-gray-700 rounded-lg shadow border border-gray-200" title="导出 JSON">
            <Download size={16} />
          </button>
        </div>
      )}

      {/* Graph Container or Empty State */}
      <div className="flex-grow w-full h-full relative bg-gray-50/30">
        <div ref={containerRef} className={`w-full h-full cursor-grab active:cursor-grabbing ${!hasData ? 'hidden' : 'block'}`} />
        
        {!hasData && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
            <div className="p-4 bg-gray-50 rounded-full mb-3">
               <FolderOpen size={40} className="text-gray-300" />
            </div>
            <p className="font-medium text-sm">暂无记忆图谱数据</p>
            <p className="text-xs mt-1 text-gray-400">请开始对话以生成记忆</p>
          </div>
        )}
      </div>
      
      {/* Overlay Info - Only show if has data */}
      {hasData && (
        <div className="absolute bottom-4 left-4 bg-white/90 backdrop-blur-sm border border-gray-200 p-3 rounded-lg text-xs text-gray-500 pointer-events-none shadow-sm">
          <div className="font-bold text-gray-800 mb-1">图谱统计 (第 {day} 天)</div>
          <div>节点: {data.nodes.length}</div>
          <div>关系: {data.edges.length}</div>
        </div>
      )}
    </div>
  );
};

export default KnowledgeGraph;
