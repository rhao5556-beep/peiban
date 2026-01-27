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
  const graphAreaRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [, setLayoutReady] = useState(false);
  const [hoverCard, setHoverCard] = useState<null | {
    kind: 'node' | 'edge';
    id: string;
    x: number;
    y: number;
    entries: Array<[string, string]>;
  }>(null);

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
            'opacity': ('mapData(weight, 0, 1, 0.3, 1)' as any) // 根据权重调整透明度
          }
        }
      ],
      layout: { name: 'grid' },
      wheelSensitivity: 0.2,
    });

    const formatValue = (value: unknown) => {
      if (value === null) return 'null';
      if (value === undefined) return '';
      if (typeof value === 'string') return value;
      if (typeof value === 'number' || typeof value === 'boolean') return String(value);
      try {
        return JSON.stringify(value);
      } catch {
        return String(value);
      }
    };

    const buildEntries = (cyData: Record<string, unknown>) => {
      const { properties, ...rest } = cyData as any;
      const props = properties && typeof properties === 'object' ? (properties as Record<string, unknown>) : {};
      const combined: Record<string, unknown> = { ...props, ...rest };
      return Object.entries(combined)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, formatValue(v)] as [string, string])
        .sort(([a], [b]) => a.localeCompare(b, 'zh-Hans-CN'));
    };

    const getRenderedPos = (evt: any): { x: number; y: number } | null => {
      const p = evt?.renderedPosition;
      if (!p || typeof p.x !== 'number' || typeof p.y !== 'number') return null;
      return { x: p.x, y: p.y };
    };

    const showHoverCard = (evt: any) => {
      const pos = getRenderedPos(evt);
      const ele = evt?.target;
      if (!pos || !ele) return;
      const d = ele.data() as Record<string, unknown>;
      setHoverCard({
        kind: ele.isNode() ? 'node' : 'edge',
        id: ele.id(),
        x: pos.x,
        y: pos.y,
        entries: buildEntries(d)
      });
    };

    const moveHoverCard = (evt: any) => {
      const pos = getRenderedPos(evt);
      const ele = evt?.target;
      if (!pos || !ele) return;
      setHoverCard(prev => {
        if (!prev || prev.id !== ele.id()) return prev;
        return { ...prev, x: pos.x, y: pos.y };
      });
    };

    const hideHoverCard = (evt: any) => {
      const ele = evt?.target;
      if (!ele) {
        setHoverCard(null);
        return;
      }
      setHoverCard(prev => (prev && prev.id === ele.id() ? null : prev));
    };

    const cy = cyRef.current;
    cy.on('mouseover', 'node,edge', showHoverCard);
    cy.on('mousemove', 'node,edge', moveHoverCard);
    cy.on('mouseout', 'node,edge', hideHoverCard);
    cy.on('zoom pan', () => setHoverCard(null));

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
        data: { id: n.id, label: n.label, type: n.type, weight: n.weight || 10, properties: n.properties }
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
          weight: e.weight || 1,  // 传递权重用于边的粗细和透明度
          properties: e.properties
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
        <div ref={graphAreaRef} className="w-full h-full relative">
          <div ref={containerRef} className={`w-full h-full cursor-grab active:cursor-grabbing ${!hasData ? 'hidden' : 'block'}`} />
          {hoverCard && (
            <div
              className="absolute z-20 pointer-events-none max-w-sm bg-white/95 backdrop-blur-sm border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs text-gray-900 max-h-64 overflow-auto"
              style={{ left: hoverCard.x + 12, top: hoverCard.y + 12 }}
            >
              <div className="font-semibold text-gray-800">
                {hoverCard.kind === 'node' ? '节点属性' : '关系属性'}
              </div>
              <div className="mt-2 space-y-1">
                {hoverCard.entries.map(([k, v]) => (
                  <div key={k} className="flex gap-2">
                    <div className="shrink-0 w-28 text-gray-500">{k}</div>
                    <div className="min-w-0 break-words">{v}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        
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
