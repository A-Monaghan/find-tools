
import React, { useState } from 'react';
import { Icon } from './Icon';

interface ApiKeyInputProps {
  apiKey: string;
  onApiKeyChange: (key: string) => void;
}

const ApiKeyInput: React.FC<ApiKeyInputProps> = ({ apiKey, onApiKeyChange }) => {
  const [showKey, setShowKey] = useState(false);

  return (
    <div className="p-4 sm:p-6 rounded-xl mb-6 bg-slate-900 border border-white/10">
      <label htmlFor="api-key" className="flex items-center text-slate-100 font-bold mb-2">
        <Icon name="key" className="w-5 h-5 mr-2 text-indigo-400" />
        OpenRouter API Key
      </label>
      <div className="relative">
        <input
          id="api-key"
          type={showKey ? 'text' : 'password'}
          value={apiKey}
          onChange={(e) => onApiKeyChange(e.target.value)}
          placeholder="Enter your OpenRouter API key (from openrouter.ai)"
          className="w-full px-4 py-3 bg-slate-900 border border-white/10 rounded-xl text-slate-200 text-sm pl-4 pr-10 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 placeholder-slate-500"
          aria-label="OpenRouter API Key"
        />
        <button
          type="button"
          onClick={() => setShowKey(!showKey)}
          className="absolute inset-y-0 right-0 px-3 flex items-center text-slate-400 hover:text-slate-200 transition-all"
          aria-label={showKey ? 'Hide API key' : 'Show API key'}
        >
          <Icon name={showKey ? 'eye-off' : 'eye'} className="w-5 h-5" />
        </button>
      </div>
      <p className="text-xs text-slate-500 mt-2 leading-relaxed">
        Your API key is stored only in your browser and is sent to the backend for analysis. Get a key at <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:text-indigo-400">openrouter.ai/keys</a>.
      </p>
    </div>
  );
};

export default ApiKeyInput;
