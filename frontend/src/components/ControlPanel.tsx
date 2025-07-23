import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ImageIcon, Sparkles, Wand2, Upload, Trash2 } from 'lucide-react';
import { toast } from "sonner";
import { Slider } from './ui/slider';
import { Switch } from './ui/switch';
import { Separator } from './ui/separator';
import { useToast } from '../hooks/use-toast';

interface ControlPanelProps {
  onGenerate: (prompt: string, files: File[], count: number, imageStrength: string, faceFiles?: File[], needConfirmation?: boolean) => Promise<void>;
  isGenerating: boolean;
  isControlPanelDisabled?: boolean;
  prompt: string;
  setPrompt: (prompt: string) => void;
  uploadedFiles: File[] | null;
  setUploadedFiles: (files: File[] | null) => void;
}

const imageStrengthLevels = [
  { value: "lowest", label: "极低" },
  { value: "low", label: "低" },
  { value: "medium", label: "中等" },
  { value: "high", label: "高" },
  { value: "highest", label: "极高" },
];

const ControlPanel: React.FC<ControlPanelProps> = ({
  onGenerate,
  isGenerating,
  isControlPanelDisabled,
  prompt,
  setPrompt,
  uploadedFiles,
  setUploadedFiles,
}: ControlPanelProps) => {
  const [outputCount, setOutputCount] = useState<number>(1);
  const [inputValue, setInputValue] = useState<string>("1");
  const [imageStrength, setImageStrength] = useState<string>(imageStrengthLevels[2].value);
  const [needConfirmation, setNeedConfirmation] = useState<boolean>(true);
  // 人脸上传状态 - 已隐藏，如需启用请取消注释
  // const [uploadedFaceFiles, setUploadedFaceFiles] = useState<File[] | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isControlPanelDisabled) return;
    const files = e.target.files;
    if (files && files.length > 0) {
      const imageFiles = Array.from(files).filter(file => file.type.startsWith('image/'));
      if (imageFiles.length > 0) {
        setUploadedFiles(imageFiles);
        if (imageFiles.length !== files.length) {
          toast.warning("部分非图片文件已被忽略。");
        }
      } else {
        toast.error("请上传至少一个图片文件");
      }
    } else {
      setUploadedFiles(null);
    }
  };

  // 人脸文件处理函数 - 已隐藏，如需启用请取消注释
  /*
  const handleFaceFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isControlPanelDisabled) return;
    const files = e.target.files;
    if (files && files.length > 0) {
      const imageFiles = Array.from(files).filter(file => file.type.startsWith('image/'));
      if (imageFiles.length > 0) {
        setUploadedFaceFiles(imageFiles);
        if (imageFiles.length !== files.length) {
          toast.warning("部分非图片文件已被忽略。");
        }
      } else {
        toast.error("请上传至少一个人脸图片文件");
      }
    } else {
      setUploadedFaceFiles(null);
    }
  };
  */

  const handleCountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isControlPanelDisabled) return;
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
    if (isControlPanelDisabled) return;
    if (inputValue === "" || isNaN(parseInt(inputValue))) {
      setOutputCount(1);
      setInputValue("1");
    }
  };

  const handleGenerateClick = () => {
    if (isControlPanelDisabled) return;
    if (!uploadedFiles || uploadedFiles.length === 0) {
      toast.error("请先上传至少一张图片");
      return;
    }
    onGenerate(prompt, uploadedFiles, outputCount, imageStrength, undefined, needConfirmation);
  };

  return (
    <div className={`flex flex-col h-full ${isControlPanelDisabled ? 'select-none' : ''}`}>
      <div className="flex-1 overflow-y-auto px-3 py-2.5 space-y-3.5">
      {/* 标题和分隔线 */}
        <div className="flex items-center gap-2">
          <Wand2 className={`w-5 h-5 text-blue-600 ${isControlPanelDisabled ? 'opacity-50' : ''}`} />
          <h2 className={`text-base font-semibold text-blue-900 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>图生图</h2>
        </div>
        
        {/* 上传图片区域 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-blue-900 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>上传图片</Label>
        <div className="relative">
          <input
            type="file"
            onChange={handleFileChange}
            accept="image/*"
            multiple
            className="hidden"
            id="image-upload"
            disabled={isControlPanelDisabled}
          />
          <label
            htmlFor="image-upload"
              className={`flex flex-col items-center justify-center w-full h-20 border-2 border-dashed rounded-lg ${isControlPanelDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-blue-400'} border-blue-200 transition-colors bg-blue-50/50`}
          >
            {uploadedFiles && uploadedFiles.length > 0 ? (
              <div className="relative w-full h-full">
                  <img 
                  src={URL.createObjectURL(uploadedFiles[0])}
                  alt="Preview"
                  className={`w-full h-full object-contain rounded-lg ${isControlPanelDisabled ? 'opacity-70' : ''}`}
                  />
                {uploadedFiles.length > 1 && (
                    <div className={`absolute bottom-1 left-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded ${isControlPanelDisabled ? 'opacity-70' : ''}`}>
                    +{uploadedFiles.length - 1} 张其他图片
                </div>
                )}
                  <Button 
                  variant="destructive"
                  size="icon"
                    className={`absolute top-1 right-1 bg-red-500/80 hover:bg-red-600/90 scale-75 ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                  onClick={(e) => {
                    if (isControlPanelDisabled) {e.preventDefault(); return;}
                    e.preventDefault();
                    setUploadedFiles(null);
                    const input = document.getElementById('image-upload') as HTMLInputElement;
                    if (input) input.value = '';
                    }}
                  disabled={isControlPanelDisabled}
                >
                    <Trash2 className="h-3 w-3" />
                  </Button>
              </div>
            ) : (
                <div className={`flex flex-col items-center justify-center text-blue-900/70 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>
                  <Upload className="w-5 h-5 mb-1" />
                  <span className="text-sm">点击或拖拽上传图片</span>
                  <span className="text-xs text-blue-900/50 mt-0.5">支持多文件</span>
                </div>
            )}
          </label>
          </div>
        </div>
        
        {/* 上传人脸功能已隐藏 - 如需启用请取消下方注释 */}
        {/*
        <div className="space-y-1.5">
          <Label className={`text-sm text-blue-900 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>上传人脸图片（可选）</Label>
          <div className="relative">
            <input
              type="file"
              onChange={handleFaceFileChange}
              accept="image/*"
              multiple
              className="hidden"
              id="face-upload"
              disabled={isControlPanelDisabled}
            />
            <label
              htmlFor="face-upload"
              className={`flex flex-col items-center justify-center w-full h-20 border-2 border-dashed rounded-lg ${isControlPanelDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-green-400'} border-green-200 transition-colors bg-green-50/50`}
            >
              {uploadedFaceFiles && uploadedFaceFiles.length > 0 ? (
                <div className="relative w-full h-full">
                  <img 
                    src={URL.createObjectURL(uploadedFaceFiles[0])}
                    alt="Face Preview"
                    className={`w-full h-full object-contain rounded-lg ${isControlPanelDisabled ? 'opacity-70' : ''}`}
                  />
                  {uploadedFaceFiles.length > 1 && (
                    <div className={`absolute bottom-1 left-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded ${isControlPanelDisabled ? 'opacity-70' : ''}`}>
                      +{uploadedFaceFiles.length - 1} 张其他人脸
                    </div>
                  )}
                  <Button 
                    variant="destructive"
                    size="icon"
                    className={`absolute top-1 right-1 bg-red-500/80 hover:bg-red-600/90 scale-75 ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    onClick={(e) => {
                      if (isControlPanelDisabled) {e.preventDefault(); return;}
                      e.preventDefault();
                      setUploadedFaceFiles(null);
                      const input = document.getElementById('face-upload') as HTMLInputElement;
                      if (input) input.value = '';
                    }}
                    disabled={isControlPanelDisabled}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <div className={`flex flex-col items-center justify-center text-green-900/70 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>
                  <User className="w-5 h-5 mb-1" />
                  <span className="text-sm">点击或拖拽上传人脸图片</span>
                  <span className="text-xs text-green-900/50 mt-0.5">用于人脸替换</span>
                </div>
              )}
            </label>
          </div>
        </div>
        */}



      {/* 提示词输入区域 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-blue-900 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>提示词</Label>
          <Textarea
            value={prompt}
          onChange={(e) => {
            if (isControlPanelDisabled) return;
            setPrompt(e.target.value)
          }}
          placeholder="请输入提示词（可选）"
            className={`min-h-[52px] text-sm bg-blue-50/50 border-blue-200 text-blue-900 placeholder:text-blue-400 ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          disabled={isControlPanelDisabled}
        />
        </div>

      {/* 图像相似度控制 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-blue-900 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>图像相似度</Label>
        <Select
          value={imageStrength}
          onValueChange={(value) => {
            if (isControlPanelDisabled) return;
            setImageStrength(value);
          }}
          disabled={isControlPanelDisabled}
        >
            <SelectTrigger className={`w-full h-8 text-sm bg-blue-50/50 border-blue-200 text-blue-900 ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
            <SelectValue placeholder="选择相似度" />
          </SelectTrigger>
            <SelectContent className="bg-white border-blue-100 text-blue-900">
            {imageStrengthLevels.map(level => (
                <SelectItem key={level.value} value={level.value} className="hover:bg-blue-50 focus:bg-blue-50 text-sm">
                {level.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      
      {/* 生成数量设置 */}
        <div className="space-y-1.5">
          <Label className={`text-sm text-blue-900 ${isControlPanelDisabled ? 'opacity-50' : ''}`}>生成数量</Label>
        <div className="relative">
          <Input
            type="number"
            min={1}
            max={16}
            value={inputValue}
            onChange={handleCountChange}
            onBlur={handleBlur}
              className={`text-sm h-8 bg-blue-50/50 border-blue-200 text-blue-900 pr-14 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            onWheel={(e) => e.currentTarget.blur()}
            disabled={isControlPanelDisabled}
            id="output-count-input"
          />
            <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
                className={`h-6 px-1 text-blue-900/70 hover:text-blue-900 hover:bg-blue-100 ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              onClick={() => {
                if (isControlPanelDisabled) return;
                const newValue = Math.max(1, outputCount - 1);
                setOutputCount(newValue);
                setInputValue(newValue.toString());
              }}
              disabled={outputCount <= 1 || isControlPanelDisabled}
            >
              -
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
                className={`h-6 px-1 text-blue-900/70 hover:text-blue-900 hover:bg-blue-100 ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              onClick={() => {
                if (isControlPanelDisabled) return;
                const newValue = Math.min(16, outputCount + 1);
                setOutputCount(newValue);
                setInputValue(newValue.toString());
              }}
              disabled={outputCount >= 16 || isControlPanelDisabled}
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
              id="need-confirmation"
              checked={needConfirmation}
              onChange={(e) => setNeedConfirmation(e.target.checked)}
              disabled={isControlPanelDisabled}
              className={`h-4 w-4 rounded border-blue-300 text-blue-600 focus:ring-blue-500 ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            />
            <Label 
              htmlFor="need-confirmation" 
              className={`text-sm text-blue-900 cursor-pointer ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
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
        disabled={isGenerating || !uploadedFiles || uploadedFiles.length === 0 || isControlPanelDisabled}
          className={`w-full h-8 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-medium rounded-lg text-sm ${isControlPanelDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
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

export default ControlPanel;
