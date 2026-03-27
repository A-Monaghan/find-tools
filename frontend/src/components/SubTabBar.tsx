/**
 * Reusable sub-tab bar for Chat, Entity Extractor, Companies House.
 */
import React from 'react';

export interface SubTab {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

interface SubTabBarProps {
  tabs: SubTab[];
  activeId: string;
  onSelect: (id: string) => void;
  accentColor?: 'green' | 'indigo' | 'orange' | 'emerald';
}

const accentClasses = {
  green: 'bg-accent text-white shadow-sm',
  indigo: 'bg-indigo-600 shadow-indigo-900/30',
  orange: 'bg-orange-600 shadow-orange-900/30',
  emerald: 'bg-emerald-600 shadow-emerald-900/30',
};

export const SubTabBar: React.FC<SubTabBarProps> = ({
  tabs,
  activeId,
  onSelect,
  accentColor = 'green',
}) => {
  const activeClass = accentClasses[accentColor];

  return (
    <div className="flex items-center gap-1 border-b border-slate-200 pb-2 mb-4">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onSelect(tab.id)}
          className={`
            flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
            ${activeId === tab.id
              ? `${activeClass}`
              : 'text-ink-muted hover:text-ink hover:bg-slate-100'
            }
          `}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
};
