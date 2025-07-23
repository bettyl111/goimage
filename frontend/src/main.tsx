// 导入React DOM的createRoot方法，用于创建React应用的根节点
import { createRoot } from 'react-dom/client'
// 导入主应用组件
import App from './App.tsx'
// 导入全局样式
import './index.css'

// 创建React应用的根节点并渲染App组件
// document.getElementById("root") 获取HTML中的根元素
// ! 表示非空断言，确保元素一定存在
createRoot(document.getElementById("root")!).render(<App />);
