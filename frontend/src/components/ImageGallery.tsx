import React from 'react';
import { Button } from '@/components/ui/button';
import { ImageIcon, Download, ZoomIn, Wand2, MessageSquareText, Trash2 } from 'lucide-react';
import { toast } from "sonner";
import { normalizeImageUrl } from '@/services/api';

export interface GeneratedImage {
  id: number | string;
  image_url: string;
  prompt: string;
  timestamp: string;
  generationType?: 'text-to-image' | 'image-to-image';
  image_filename?: string;
}

interface ImageGalleryProps {
  images: GeneratedImage[];
  openImageModal?: (imageUrl: string) => void; // 可选，如果希望主图库也支持点击放大
}

const ImageGallery = ({ images, openImageModal }: ImageGalleryProps) => {

  const handleDownloadImage = async (imageUrl: string, prompt: string) => {
    try {
      // 使用normalizeImageUrl处理图片URL
      const normalizedUrl = normalizeImageUrl(imageUrl);
      const response = await fetch(normalizedUrl);
      if (!response.ok) throw new Error('网络响应错误');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      // 基于 prompt 生成一个更友好的文件名
      const safePrompt = prompt.length > 30 ? prompt.substring(0, 30) : prompt;
      const filename = normalizedUrl.split('/').pop() || 'image.png';
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success("下载已开始");
    } catch (error) {
      console.error("下载图片失败:", error);
      toast.error("下载图片失败");
    }
  };

  if (images.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-blue-900/70">
        <ImageIcon className="w-24 h-24 mb-6 opacity-30" />
        <h3 className="text-2xl font-semibold mb-2">尚未生成图像</h3>
        <p className="text-md">请在左侧面板操作以上传图片并输入提示词来生成您的AI艺术作品。</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-hidden">
        <div className="h-full max-h-[calc(100vh-180px)] overflow-y-auto pr-2 custom-scrollbar">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {images.map((image, index) => (
              <div 
                key={image.id || index}
                className="relative group aspect-square bg-white border border-blue-100 rounded-lg overflow-hidden shadow-lg cursor-pointer transition-all duration-300 ease-in-out hover:shadow-blue-200 hover:border-blue-200"
                onClick={() => openImageModal && openImageModal(normalizeImageUrl(image.image_url))}
                >
          <img
                  src={normalizeImageUrl(image.image_url)} 
                  alt={image.prompt || 'Generated image'} 
                  className="w-full h-full object-contain transition-transform duration-300 ease-in-out group-hover:scale-105"
                  loading="lazy"
                  onError={(e) => {
                    console.warn(`Failed to load image: ${normalizeImageUrl(image.image_url)}`);
                    const imgElement = e.currentTarget as HTMLImageElement;
                    imgElement.style.display = 'none';
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'w-full h-full flex items-center justify-center bg-gray-100 text-red-500';
                    errorDiv.innerHTML = `<div class="text-center p-2"><div>图片加载失败</div></div>`;
                    imgElement.parentNode?.appendChild(errorDiv);
                  }}
          />
                {image.generationType && (
                  <div className="absolute top-1.5 left-1.5 p-1 rounded-full flex items-center justify-center text-blue-600">
                    {image.generationType === 'text-to-image' ? 
                      <MessageSquareText className="w-3 h-3 drop-shadow-md" /> : 
                      <Wand2 className="w-3 h-3 drop-shadow-md" />
                    }
                  </div>
                )}
                  <div className="absolute inset-0 bg-blue-900/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-4">
                    {openImageModal && (
                    <Button variant="ghost" size="icon" className="bg-white/90 hover:bg-white text-blue-600 hover:text-blue-700" onClick={(e) => { e.stopPropagation(); openImageModal(normalizeImageUrl(image.image_url)); }}>
                        <ZoomIn className="w-5 h-5" />
              </Button>
                    )}
                  <Button variant="ghost" size="icon" className="bg-white/90 hover:bg-white text-blue-600 hover:text-blue-700" onClick={(e) => { e.stopPropagation(); handleDownloadImage(image.image_url, image.prompt); }}>
              <Download className="w-5 h-5" />
            </Button>
                </div>
                <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-blue-900/80 to-transparent">
                  <p className="text-xs text-white truncate" title={image.prompt}>{image.prompt || '-'}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        </div>
    </div>
  );
};

export default ImageGallery;
