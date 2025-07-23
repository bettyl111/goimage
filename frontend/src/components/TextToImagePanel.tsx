import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Sparkles, MessageSquareText, Upload, Trash2, User } from 'lucide-react';
import { toast } from "sonner";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';

interface TextToImagePanelProps {
  onGenerate: (prompt: string, count: number, aspectRatio: string, referenceImage: File | null, faceImages?: File[] | null, needConfirmation?: boolean) => Promise<void>;
  isGenerating: boolean;
  isPanelDisabled?: boolean;
}

// Updated aspect ratios (removed 16:9 for now, can be added back or put in a dropdown if preferred)
const aspectRatios = [
  { value: "1:1", label: "1:1" },
  { value: "3:2", label: "3:2" },
  { value: "2:3", label: "2:3" },
  { value: "4:3", label: "4:3" },
  { value: "3:4", label: "3:4" },
  { value: "9:16", label: "9:16" }, // This one is quite tall, ensure it fits visually
];

// Helper function to calculate visual dimensions for the preview block
const calculateVisualDimensions = (ratioStr: string, maxWidth: number, maxHeight: number): { width: number; height: number } => {
  const [arW, arH] = ratioStr.split(':').map(Number);
  if (isNaN(arW) || isNaN(arH) || arW <= 0 || arH <= 0) {
    // Fallback for invalid ratio string (should not happen with predefined valid ratios)
    return { width: Math.min(maxWidth, maxHeight), height: Math.min(maxWidth, maxHeight) };
  }

  let width, height;
  // Calculate height if width is maxed out
  const heightIfWidthMax = (arH / arW) * maxWidth;
  // Calculate width if height is maxed out
  const widthIfHeightMax = (arW / arH) * maxHeight;

  if (heightIfWidthMax <= maxHeight) {
    // Width is the constraining dimension
    width = maxWidth;
    height = heightIfWidthMax;
  } else {
    // Height is the constraining dimension
    height = maxHeight;
    width = widthIfHeightMax;
  }
  return { width: Math.floor(width), height: Math.floor(height) }; // Use Math.floor to ensure it fits
};

const TextToImagePanel: React.FC<TextToImagePanelProps> = ({
  onGenerate,
  isGenerating,
  isPanelDisabled,
}) => {
  const [prompt, setPrompt] = useState<string>('');
  const [outputCount, setOutputCount] = useState<number>(1);
  const [inputValue, setInputValue] = useState<string>("1");
  const [selectedAspectRatio, setSelectedAspectRatio] = useState<string>(aspectRatios[0].value);
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [faceImages, setFaceImages] = useState<File[] | null>(null);
  const [needConfirmation, setNeedConfirmation] = useState<boolean>(true);

  const handleReferenceImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isPanelDisabled) return;
    const files = e.target.files;
    if (files && files.length > 0) {
      const imageFile = files[0];
      if (imageFile.type.startsWith('image/')) {
        setReferenceImage(imageFile);
      } else {
        toast.error("请上传一个图片文件作为参考图像。");
        setReferenceImage(null);
        e.target.value = '';
      }
    } else {
      setReferenceImage(null);
    }
  };

  const handleFaceImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      // 限制最多上传2个人脸文件
      const selectedFiles = Array.from(files).slice(0, 2);
      setFaceImages(selectedFiles);
    } else {
      setFaceImages([]);
    }
  };

  const handleCountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isPanelDisabled) return;
    const value = e.target.value;
    setInputValue(value);
    
    const numValue = parseInt(value);
    if (!isNaN(numValue)) {
      if (numValue < 1) {
        setOutputCount(1);
        setInputValue("1");
      } else if (numValue > 16) {
        setOutputCount(16);
        setInputValue("16");
      } else {
        setOutputCount(numValue);
      }
    }
  };

  const handleBlur = () => {
    if (isPanelDisabled) return;
    if (inputValue === "" || isNaN(parseInt(inputValue))) {
      setOutputCount(1);
      setInputValue("1");
    }
  };

  const handleGenerateClick = async () => {
    if (!prompt) {
      toast.error("请输入提示词(中文)");
      return;
    }

    // 调用父组件的生成函数
    onGenerate(prompt, outputCount, selectedAspectRatio, referenceImage, faceImages, needConfirmation);
  };

  return (
    <div className={`flex flex-col h-full ${isPanelDisabled ? 'select-none' : ''}`}>
      <div className="flex-1 overflow-y-auto px-3 py-2.5 space-y-3.5">
        {/* 标题和分隔线 */}
        <div className="flex items-center gap-2">
          <MessageSquareText className={`w-5 h-5 text-blue-600 ${isPanelDisabled ? 'opacity-50' : ''}`} />
          <h2 className={`text-base font-semibold text-gray-900 ${isPanelDisabled ? 'opacity-50' : ''}`}>文生图</h2>
        </div>

        {/* 提示词输入区域 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-gray-700 ${isPanelDisabled ? 'opacity-50' : ''}`}>提示词</Label>
          <Textarea
            value={prompt}
            onChange={(e) => {
              if (isPanelDisabled) return;
              setPrompt(e.target.value)
            }}
            placeholder="请输入提示词"
            className={`min-h-[120px] text-sm bg-gray-50 border-gray-200 text-gray-900 placeholder:text-gray-400 ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            disabled={isPanelDisabled}
          />
        </div>

        {/* 参考图片上传 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-gray-700 ${isPanelDisabled ? 'opacity-50' : ''}`}>参考图片（可选）</Label>
          <div className="relative">
            <input
              type="file"
              onChange={handleReferenceImageChange}
              accept="image/*"
              className="hidden"
              id="reference-image-upload"
              disabled={isPanelDisabled}
            />
            <label
              htmlFor="reference-image-upload"
              className={`flex flex-col items-center justify-center w-full h-20 border-2 border-dashed rounded-lg ${isPanelDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-blue-400'} border-gray-200 transition-colors bg-gray-50`}
            >
              {referenceImage ? (
                <div className="relative w-full h-full">
                  <img 
                    src={URL.createObjectURL(referenceImage)}
                    alt="Reference"
                    className={`w-full h-full object-contain rounded-lg ${isPanelDisabled ? 'opacity-70' : ''}`}
                  />
                  <Button 
                    variant="destructive"
                    size="icon"
                    className={`absolute top-1 right-1 bg-red-500/80 hover:bg-red-600/90 scale-75 ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    onClick={(e) => {
                      if (isPanelDisabled) {e.preventDefault(); return;}
                      e.preventDefault();
                      setReferenceImage(null);
                      const input = document.getElementById('reference-image-upload') as HTMLInputElement;
                      if (input) input.value = '';
                    }}
                    disabled={isPanelDisabled}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <div className={`flex flex-col items-center justify-center text-gray-500 ${isPanelDisabled ? 'opacity-50' : ''}`}>
                  <Upload className="w-5 h-5 mb-1" />
                  <span className="text-sm">点击或拖拽上传参考图片</span>
                  <span className="text-xs text-gray-400 mt-0.5">可选</span>
                </div>
              )}
            </label>
          </div>
        </div>

        {/* 参考人脸图片上传 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-gray-700 ${isPanelDisabled ? 'opacity-50' : ''}`}>人脸参考图片（可选）</Label>
          
          {/* 当没有选择任何图片时，显示单个上传区域 */}
          {(!faceImages || faceImages.length === 0) && (
            <div className="relative">
              <input
                type="file"
                onChange={handleFaceImageChange}
                accept="image/*"
                multiple
                className="hidden"
                id="reference-face-upload"
                disabled={isPanelDisabled}
              />
              <label
                htmlFor="reference-face-upload"
                className={`flex flex-col items-center justify-center w-full h-20 border-2 border-dashed rounded-lg ${isPanelDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-green-400'} border-green-200 transition-colors bg-green-50/50`}
              >
                <div className={`flex flex-col items-center justify-center text-green-700/70 ${isPanelDisabled ? 'opacity-50' : ''}`}>
                  <User className="w-5 h-5 mb-1" />
                  <span className="text-sm">点击或拖拽上传人脸参考图片</span>
                  <span className="text-xs text-green-600/50 mt-0.5">支持最多2个人脸按顺序</span>
                </div>
              </label>
            </div>
          )}

          {/* 当已选择图片时，显示已选择的图片和可选的第二个上传区域 */}
          {faceImages && faceImages.length > 0 && (
            <div className="grid grid-cols-2 gap-2">
              {/* 第一张图片 */}
              <div className="relative">
                <div className="relative w-full h-20 border-2 border-green-300 rounded-lg overflow-hidden bg-green-50/50">
                  <img 
                    src={URL.createObjectURL(faceImages[0])}
                    alt="Face Reference 1"
                    className={`w-full h-full object-cover ${isPanelDisabled ? 'opacity-70' : ''}`}
                  />
                  <Button 
                    variant="destructive"
                    size="icon"
                    className={`absolute top-1 right-1 bg-red-500/80 hover:bg-red-600/90 scale-75 ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    onClick={(e) => {
                      if (isPanelDisabled) {e.preventDefault(); return;}
                      e.preventDefault();
                      if (faceImages.length === 1) {
                        setFaceImages(null);
                      } else {
                        setFaceImages([faceImages[1]]);
                      }
                      const input = document.getElementById('reference-face-upload') as HTMLInputElement;
                      if (input) input.value = '';
                    }}
                    disabled={isPanelDisabled}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                  <div className="absolute bottom-1 left-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
                    人脸1
                  </div>
                </div>
              </div>

              {/* 第二张图片或上传区域 */}
              <div className="relative">
                {faceImages.length > 1 ? (
                  <div className="relative w-full h-20 border-2 border-green-300 rounded-lg overflow-hidden bg-green-50/50">
                    <img 
                      src={URL.createObjectURL(faceImages[1])}
                      alt="Face Reference 2"
                      className={`w-full h-full object-cover ${isPanelDisabled ? 'opacity-70' : ''}`}
                    />
                    <Button 
                      variant="destructive"
                      size="icon"
                      className={`absolute top-1 right-1 bg-red-500/80 hover:bg-red-600/90 scale-75 ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                      onClick={(e) => {
                        if (isPanelDisabled) {e.preventDefault(); return;}
                        e.preventDefault();
                        setFaceImages([faceImages[0]]);
                        const input = document.getElementById('reference-face-upload-2') as HTMLInputElement;
                        if (input) input.value = '';
                      }}
                      disabled={isPanelDisabled}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                    <div className="absolute bottom-1 left-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
                      人脸2
                    </div>
                  </div>
                ) : (
                  <div className="relative">
                    <input
                      type="file"
                      onChange={(e) => {
                        if (isPanelDisabled) return;
                        const files = e.target.files;
                        if (files && files.length > 0) {
                          const newFile = files[0];
                          if (newFile.type.startsWith('image/')) {
                            setFaceImages([faceImages[0], newFile]);
                          } else {
                            toast.error("请上传一个图片文件作为人脸参考。");
                            e.target.value = '';
                          }
                        }
                      }}
                      accept="image/*"
                      className="hidden"
                      id="reference-face-upload-2"
                      disabled={isPanelDisabled}
                    />
                    <label
                      htmlFor="reference-face-upload-2"
                      className={`flex flex-col items-center justify-center w-full h-20 border-2 border-dashed rounded-lg ${isPanelDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-green-400'} border-green-200 transition-colors bg-green-50/30`}
                    >
                      <div className={`flex flex-col items-center justify-center text-green-700/70 ${isPanelDisabled ? 'opacity-50' : ''}`}>
                        <User className="w-4 h-4 mb-0.5" />
                        <span className="text-xs">添加第二张人脸</span>
                        <span className="text-xs text-green-600/40">可选</span>
                      </div>
                    </label>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* 图片尺寸设置 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-gray-700 ${isPanelDisabled ? 'opacity-50' : ''}`}>图片尺寸</Label>
          <div className="grid grid-cols-3 gap-2">
            {aspectRatios.map(option => (
              <button
                key={option.value}
                onClick={() => {
                  if (isPanelDisabled) return;
                  setSelectedAspectRatio(option.value);
                }}
                className={`relative p-2 rounded border ${
                  selectedAspectRatio === option.value
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 bg-gray-50 hover:border-blue-300'
                } ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                disabled={isPanelDisabled}
              >
                <div className="flex flex-col items-center gap-1">
                  <div className="relative w-16 h-16 flex items-center justify-center">
                    <div
                      className={`bg-blue-100 border ${
                        selectedAspectRatio === option.value
                          ? 'border-blue-300'
                          : 'border-gray-300'
                      }`}
                      style={{
                        ...calculateVisualDimensions(option.value, 60, 60),
                        maxWidth: '60px',
                        maxHeight: '60px'
                      }}
                    />
                  </div>
                  <span className="text-xs text-gray-600">{option.label}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 生成数量设置 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-gray-700 ${isPanelDisabled ? 'opacity-50' : ''}`}>生成数量</Label>
          <div className="relative">
            <Input
              type="number"
              min={1}
              max={16}
              value={inputValue}
              onChange={handleCountChange}
              onBlur={handleBlur}
              className={`text-sm h-8 bg-gray-50 border-gray-200 text-gray-900 pr-14 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              onWheel={(e) => e.currentTarget.blur()}
              disabled={isPanelDisabled}
              id="output-count-input"
            />
            <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className={`h-6 px-1 text-gray-600 hover:text-blue-600 hover:bg-gray-100 ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                onClick={() => {
                  if (isPanelDisabled) return;
                  const newValue = Math.max(1, outputCount - 1);
                  setOutputCount(newValue);
                  setInputValue(newValue.toString());
                }}
                disabled={outputCount <= 1 || isPanelDisabled}
              >
                -
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className={`h-6 px-1 text-gray-600 hover:text-blue-600 hover:bg-gray-100 ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                onClick={() => {
                  if (isPanelDisabled) return;
                  const newValue = Math.min(16, outputCount + 1);
                  setOutputCount(newValue);
                  setInputValue(newValue.toString());
                }}
                disabled={outputCount >= 16 || isPanelDisabled}
              >
                +
              </Button>
            </div>
          </div>
        </div>
        
        {/* 确认选项 */}
        {outputCount > 1 && (
          <div className="flex items-center space-x-2 mt-2">
            <input
              type="checkbox"
              id="need-confirmation-text"
              checked={needConfirmation}
              onChange={(e) => setNeedConfirmation(e.target.checked)}
              disabled={isPanelDisabled}
              className={`h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            />
            <Label 
              htmlFor="need-confirmation-text" 
              className={`text-sm text-gray-700 cursor-pointer ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              生成第一张图后需确认再生成后续图片
            </Label>
          </div>
        )}
      </div>

      {/* 生成按钮 - 固定在底部 */}
      <div className="shrink-0 px-3 pb-3 pt-2">
        <Button
          onClick={handleGenerateClick}
          disabled={isGenerating || !prompt || isPanelDisabled}
          className={`w-full h-8 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg text-sm ${isPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {isGenerating ? (
            <div className="flex items-center space-x-1.5">
              <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>生成中...</span>
            </div>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />
              生成
            </>
          )}
        </Button>
      </div>
    </div>
  );
};

export default TextToImagePanel; 