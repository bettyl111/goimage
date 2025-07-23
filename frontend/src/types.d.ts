declare module 'sonner' {
  export interface ToastProps {
    id?: string | number;
    title?: React.ReactNode;
    description?: React.ReactNode;
    icon?: React.ReactNode;
    action?: React.ReactNode;
    cancel?: React.ReactNode;
    onDismiss?: () => void;
    onAutoClose?: () => void;
    duration?: number;
    className?: string;
    style?: React.CSSProperties;
    position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'top-center' | 'bottom-center';
    important?: boolean;
    dismissible?: boolean;
  }

  export interface ToastOptions extends Omit<ToastProps, 'title' | 'description'> {
    promise?: Promise<any>;
    loading?: React.ReactNode;
    success?: React.ReactNode | ((data: any) => React.ReactNode);
    error?: React.ReactNode | ((error: any) => React.ReactNode);
  }

  export interface ToasterProps {
    position?: ToastProps['position'];
    hotkey?: string[];
    richColors?: boolean;
    expand?: boolean;
    duration?: number;
    visibleToasts?: number;
    closeButton?: boolean;
    toastOptions?: ToastOptions;
    className?: string;
    style?: React.CSSProperties;
    theme?: 'light' | 'dark' | 'system';
  }

  export function Toaster(props?: ToasterProps): JSX.Element;
  export function toast(message: React.ReactNode, options?: ToastOptions): void;
  export function toast(options: ToastOptions & { description?: React.ReactNode }): void;

  export namespace toast {
    function success(message: React.ReactNode, options?: ToastOptions): void;
    function error(message: React.ReactNode, options?: ToastOptions): void;
    function warning(message: React.ReactNode, options?: ToastOptions): void;
    function info(message: React.ReactNode, options?: ToastOptions): void;
    function loading(message: React.ReactNode, options?: ToastOptions): void;
    function custom(message: React.ReactNode, options?: ToastOptions): void;
    function promise<T = any>(promise: Promise<T>, options?: ToastOptions): Promise<T>;
    function dismiss(id?: string | number): void;
    function message(message: React.ReactNode, options?: ToastOptions): void;
  }
} 