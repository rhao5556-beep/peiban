import React from 'react';
import { Smile, ThumbsUp, ThumbsDown, X } from 'lucide-react';

interface MemeDisplayProps {
  description: string;
  imageUrl?: string;
  onFeedback: (action: 'liked' | 'disliked' | 'ignored') => void;
}

const MemeDisplay: React.FC<MemeDisplayProps> = ({ 
  description, 
  imageUrl, 
  onFeedback 
}) => {
  return (
    <div className="bg-gradient-to-br from-yellow-50 to-orange-50 rounded-lg p-4 border-2 border-yellow-200 my-2">
      <div className="flex items-start gap-3">
        <Smile className="text-yellow-500 flex-shrink-0 mt-1" size={20} />
        <div className="flex-grow">
          <p className="text-gray-800 text-sm mb-2">{description}</p>
          {imageUrl && (
            <img 
              src={imageUrl} 
              alt="表情包" 
              className="max-w-xs rounded-lg shadow-sm"
            />
          )}
        </div>
      </div>
      
      <div className="flex gap-2 mt-3 justify-end">
        <button
          onClick={() => onFeedback('liked')}
          className="p-2 hover:bg-green-100 rounded-lg transition-colors"
          title="喜欢"
        >
          <ThumbsUp size={16} className="text-green-600" />
        </button>
        <button
          onClick={() => onFeedback('disliked')}
          className="p-2 hover:bg-red-100 rounded-lg transition-colors"
          title="不喜欢"
        >
          <ThumbsDown size={16} className="text-red-600" />
        </button>
        <button
          onClick={() => onFeedback('ignored')}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          title="忽略"
        >
          <X size={16} className="text-gray-600" />
        </button>
      </div>
    </div>
  );
};

export default MemeDisplay;
