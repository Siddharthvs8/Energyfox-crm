"use client";

import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface PipelineData {
  key: string;
  label: string;
  color: string;
  value: number;
}

export default function PipelineChart({ data }: { data: PipelineData[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-300">
        <span className="text-sm">No pipeline data</span>
      </div>
    );
  }

  // Custom Tooltip for the Pipeline Chart
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-lg min-w-[120px]">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">{data.label}</p>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: data.color }}></div>
            <p className="text-lg font-bold text-slate-900">{data.value}</p>
          </div>
        </div>
      );
    }
    return null;
  };

  // Truncate long labels for the X-axis
  const formatXAxis = (tickItem: string) => {
    if (tickItem.length > 8) {
      return tickItem.substring(0, 8) + '...';
    }
    return tickItem;
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart 
        data={data} 
        margin={{ top: 20, right: 10, left: -20, bottom: 40 }}
        barCategoryGap="15%"
      >
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
        <XAxis 
          dataKey="label" 
          axisLine={false} 
          tickLine={false} 
          tick={{ fontSize: 9, fill: '#94a3b8', fontWeight: 600 }} 
          dy={10}
          dx={-5}
          interval={0}
          angle={-45}
          textAnchor="end"
          tickFormatter={formatXAxis}
        />
        <YAxis 
          axisLine={false} 
          tickLine={false} 
          tick={{ fontSize: 11, fill: '#94a3b8', fontWeight: 500 }}
          allowDecimals={false}
          dx={-10}
        />
        <Tooltip cursor={{ fill: '#f8fafc' }} content={<CustomTooltip />} />
        <Bar 
          dataKey="value" 
          radius={[6, 6, 0, 0]}
          animationDuration={1500}
        >
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
