import json
import os
import random
import config
import logging

logger = logging.getLogger(__name__)

from typing import Optional, Dict, List

# --- Helper 函数: 用户目录名生成 ---
def get_user_directory_name(current_user: Dict, record_user_email: Optional[str] = None) -> str:
    """
    统一的用户目录名生成逻辑
    
    规则：
    1. 域账号用户：直接使用域用户名（如 'aaa'）
    2. 邮箱用户：使用邮箱转换格式（如 'aaa@mail.com' -> 'aaa_at_mail_dot_com'）
    3. 历史记录兼容：如果记录中的user_email与当前用户不同类型，使用记录的格式
    
    Args:
        current_user: 当前登录用户信息
        record_user_email: 历史记录中的用户邮箱（用于兼容性处理）
    
    Returns:
        用户目录名字符串
    """
    user_email = current_user["email"]
    username = current_user.get("username", user_email)
    user_role = current_user.get("role", "user")
    
    # 如果提供了历史记录的用户邮箱，需要检查兼容性
    if record_user_email:
        # 如果当前用户是域账号，但历史记录是邮箱格式
        if user_role == "domain_user" and "@" in record_user_email:
            # 检查是否是同一个用户的不同登录方式
            domain_name = username
            email_prefix = record_user_email.split("@")[0]
            
            if domain_name == email_prefix:
                # 同一个用户，使用邮箱格式（向后兼容）
                return record_user_email.replace('@', '_at_').replace('.', '_dot_')
            else:
                # 不同用户，使用当前用户的格式
                return username if user_role == "domain_user" else record_user_email.replace('@', '_at_').replace('.', '_dot_')
        
        # 如果当前用户是邮箱，但历史记录是域账号格式
        elif user_role != "domain_user" and "@" not in record_user_email:
            # 检查是否是同一个用户的不同登录方式
            email_prefix = user_email.split("@")[0]
            
            if email_prefix == record_user_email:
                # 同一个用户，使用域账号格式（保持一致性）
                return record_user_email
            else:
                # 不同用户，使用当前用户的格式
                return user_email.replace('@', '_at_').replace('.', '_dot_')
    
    # 标准处理逻辑
    if user_role == "domain_user":
        # 域账号用户：直接使用域用户名
        return username
    else:
        # 邮箱用户：转换邮箱格式
        return user_email.replace('@', '_at_').replace('.', '_dot_')


def calculate_dimensions(aspect_ratio_str: str, longest_edge: int = 1024) -> tuple[int, int]:
    try:
        ar_w, ar_h = map(int, aspect_ratio_str.split(':'))
        if ar_w <= 0 or ar_h <= 0:
            raise ValueError("Aspect ratio parts must be positive")
    except ValueError as e:
        logger.error(f"无法解析长宽比字符串: '{aspect_ratio_str}'. 错误: {e}. 使用默认 1:1.")
        ar_w, ar_h = 1, 1 # Default to 1:1 on error

    if ar_w == ar_h:
        width = longest_edge
        height = longest_edge
    elif ar_w > ar_h: # Landscape or square
        width = longest_edge
        height = int(round(longest_edge * (ar_h / ar_w)))
    else: # Portrait
        height = longest_edge
        width = int(round(longest_edge * (ar_w / ar_h)))

    # Ensure dimensions are multiples of 8 (common for diffusion models)
    # And not zero if original calculation was too small (e.g. very extreme aspect ratio and small longest_edge)
    width = max(64, int(round(width / 8.0) * 8))
    height = max(64, int(round(height / 8.0) * 8))
    
    logger.info(f"根据长宽比 '{aspect_ratio_str}' 和最长边 {longest_edge} 计算出尺寸: {width}x{height}")
    return width, height


# --- Helper 函数: 与 ComfyUI 交互 ---
def modify_comfyui_workflow(workflow_json_path: str, input_image_path: str, prompt: str, image_strength: str, face_files: Optional[list] = None) -> dict:
    with open(workflow_json_path, 'r') as f:
        workflow = json.load(f)

    if config.I2I_NODE_ID_LOAD_IMAGE in workflow:
        workflow[config.I2I_NODE_ID_LOAD_IMAGE]["inputs"]["image"] = os.path.basename(input_image_path)
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到加载图像节点 '{config.I2I_NODE_ID_LOAD_IMAGE}'")

    if config.I2I_NODE_ID_PROMPT_TEXT in workflow:
        if prompt:
            workflow[config.I2I_NODE_ID_PROMPT_TEXT]["inputs"]["text"] = prompt # Assuming positive prompt
        else:
            workflow[config.I2I_NODE_ID_PROMPT_TEXT]["inputs"]["text"] = "" 
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到提示词节点 '{config.I2I_NODE_ID_PROMPT_TEXT}'")
    
    if config.I2I_NODE_ID_IMAGE_STRENGTH in workflow and \
       "inputs" in workflow[config.I2I_NODE_ID_IMAGE_STRENGTH] and \
       "image_strength" in workflow[config.I2I_NODE_ID_IMAGE_STRENGTH]["inputs"]:
        workflow[config.I2I_NODE_ID_IMAGE_STRENGTH]["inputs"]["image_strength"] = image_strength
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到图像强度节点 '{config.I2I_NODE_ID_IMAGE_STRENGTH}' 或其 'image_strength' 输入。")

    if config.I2I_NODE_ID_KSAMPLER_SEED in workflow:
        workflow[config.I2I_NODE_ID_KSAMPLER_SEED]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到种子节点 '{config.I2I_NODE_ID_KSAMPLER_SEED}'")
    
    # 处理人脸文件（如果提供了的话）
    if face_files and len(face_files) > 0:
        # 获取人脸相关节点ID（需要在config中配置）
        face_node_ids = getattr(config, 'I2I_FACE_NODE_IDS', {})
        
        if face_node_ids:
            for i, face_file in enumerate(face_files):
                if i < 5:  # 最多支持5个人脸
                    face_load_node_id = face_node_ids.get(f"load_face_{i}")
                    if face_load_node_id and face_load_node_id in workflow:
                        workflow[face_load_node_id]["inputs"]["image"] = os.path.basename(face_file)
                        logger.info(f"人脸文件 {i+1} '{os.path.basename(face_file)}' 已设置到加载节点 '{face_load_node_id}'")
                    elif face_load_node_id:
                        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到人脸图像加载节点 '{face_load_node_id}'. 人脸文件 {i+1} 可能不会生效。")
                    else:
                        logger.warning(f"未配置人脸图像加载节点ID (I2I_FACE_NODE_IDS.load_face_{i})，人脸文件 {i+1} 将被忽略。")
                
            # 配置人脸替换/融合节点（如果配置了的话）
            face_swap_node_id = face_node_ids.get("face_swap")
            if face_swap_node_id and face_swap_node_id in workflow:
                workflow[face_swap_node_id]["inputs"]["enabled"] = True
                logger.info(f"人脸替换节点 '{face_swap_node_id}' 已启用")
                
            logger.info(f"为图生图工作流添加 {len(face_files)} 个人脸文件")
        else:
            # 向后兼容：使用旧的单个节点配置
            if config.I2I_FACE_NODE_ID_LOAD_FACE in workflow:
                workflow[config.I2I_FACE_NODE_ID_LOAD_FACE]["inputs"]["image"] = os.path.basename(face_files[0])
                logger.info(f"使用向后兼容模式：人脸文件 '{os.path.basename(face_files[0])}' 已设置到节点 '{config.I2I_FACE_NODE_ID_LOAD_FACE}'")
            
            if config.I2I_FACE_NODE_ID_FACE_SWAP in workflow:
                workflow[config.I2I_FACE_NODE_ID_FACE_SWAP]["inputs"]["enabled"] = True
                logger.info(f"使用向后兼容模式：人脸替换节点 '{config.I2I_FACE_NODE_ID_FACE_SWAP}' 已启用")
        
    return workflow



def modify_text_to_image_workflow(
    workflow_json_path: str, 
    prompt: str, 
    aspect_ratio: str, # Changed from size
    reference_image_filename: Optional[str] = None,
    face_image_filenames: Optional[list[str]] = None
) -> dict:
    with open(workflow_json_path, 'r') as f:
        workflow = json.load(f)

    is_pose_workflow = reference_image_filename is not None
    has_face_images = face_image_filenames is not None and len(face_image_filenames) > 0
    actual_width, actual_height = calculate_dimensions(aspect_ratio_str=aspect_ratio, longest_edge=1024)

    prompt_node_id = config.T2I_NODE_ID_PROMPT_TEXT
    empty_latent_node_id = config.T2I_NODE_ID_EMPTY_LATENT
    flux_forward_model_node_id = config.T2I_NODE_ID_Flux_FORWARD_MODEL
    pulid1_node_id = config.T2I_NODE_ID_PULID_MODEL1
    pulid2_node_id = config.T2I_NODE_ID_PULID_MODEL2
    first_block_node_id = config.T2I_NODE_ID_FIRST_BLOCK_MODEL
    ksampler_seed_node_id = config.T2I_NODE_ID_KSAMPLER_SEED
    load_ref_image_node_id = config.T2I_NODE_ID_LOAD_REFERENCE_IMAGE
    resize_ref_image_node_id = config.T2I_NODE_ID_RESIZE_IMAGE
    # input_resize_node_id = config.T2I_NODE_ID_INPUT_RESIZE

    flux_clip_node_id = config.T2I_NODE_ID_FLUXGUIDANCE
    instruct_node_id = config.T2I_NODE_ID_INSTRUCT
    basic_guider_node_id = config.T2I_NODE_ID_BASIC_GUIDER

    if '<english>' in prompt: 
        workflow["23"]["inputs"]['text'][0] = "257"
        prompt = prompt.replace('<english>','')
    else:
        workflow["23"]["inputs"]['text'][0] = "256"

    logger.info(prompt)


    if prompt_node_id in workflow:
        workflow[prompt_node_id]["inputs"]["text"] = prompt
    else:
        logger.warning(f"文生图工作流 {workflow_json_path} 中未找到提示词节点 '{prompt_node_id}'")

    if ksampler_seed_node_id in workflow:
        workflow[ksampler_seed_node_id]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
    else:
        logger.warning(f"文生图工作流 {workflow_json_path} 中未找到种子节点 '{ksampler_seed_node_id}'")

    # 处理参考图片
    if is_pose_workflow:
        workflow[basic_guider_node_id]["inputs"]['conditioning'][0] = instruct_node_id # p2p controlnet
    else:
        workflow[basic_guider_node_id]["inputs"]['conditioning'][0] = flux_clip_node_id
        reference_image_filename = os.path.join(config.COMFYUI_INPUT_DIR, '00012.jpg') # init empty image


    if load_ref_image_node_id in workflow:
        workflow[load_ref_image_node_id]["inputs"]["image"] = reference_image_filename
        logger.info(f"参考图像 '{reference_image_filename}' 已设置到加载节点 '{load_ref_image_node_id}'")
        
        if resize_ref_image_node_id and resize_ref_image_node_id in workflow:
            try:
                workflow[resize_ref_image_node_id]["inputs"]["width"] = actual_width
                workflow[resize_ref_image_node_id]["inputs"]["height"] = actual_height
                logger.info(f"参考图像缩放节点 '{resize_ref_image_node_id}' 尺寸设置为: {actual_width}x{actual_height}")
            except KeyError as e:
                logger.warning(f"姿势参考工作流 {workflow_json_path} 中参考图像缩放节点 '{resize_ref_image_node_id}' 缺少 width/height 输入: {e}")
        elif resize_ref_image_node_id:
             logger.warning(f"姿势参考工作流 {workflow_json_path} 中未找到已配置的参考图像缩放节点 '{resize_ref_image_node_id}'.")
    else:
        logger.warning(f"姿势参考工作流 {workflow_json_path} 中未找到参考图像加载节点 '{load_ref_image_node_id}'. 参考图像可能不会生效。")


    if 'nsfw' in prompt[:10]: #set nsfw lora
        workflow["244"]["inputs"]['lora_03'] = "NSFW_master.safetensors"
        workflow["244"]["inputs"]['strength_03'] = 0.8
        workflow["244"]["inputs"]['lora_02'] = "feet_fetish_LoRA__for_Flux.safetensors"
        workflow["244"]["inputs"]['strength_02'] = 1.0
    else:
        workflow["244"]["inputs"]['lora_03'] = "None"

    if '<zilcova>' in prompt: #set id lora
        workflow["244"]["inputs"]['lora_04'] = "flux-zilcova.safetensors"
        workflow["244"]["inputs"]['strength_04'] = 1.2
    elif '<merry>' in prompt: #set id lora
        workflow["244"]["inputs"]['lora_04'] = "merry.safetensors"
        workflow["244"]["inputs"]['strength_04'] = 1.0
    else:
        workflow["244"]["inputs"]['lora_04'] = "None"

    

    

    # 处理人脸图片
    if has_face_images:
        # 获取人脸相关节点ID（需要在config中配置）
        face_node_ids = getattr(config, 'T2I_FACE_NODE_IDS', {})
        logger.info(f'face count {len(face_image_filenames)}')

        if len(face_image_filenames) == 0:
            workflow[first_block_node_id]["inputs"]['model'][0] = flux_forward_model_node_id
        elif len(face_image_filenames) == 1:
            workflow[first_block_node_id]["inputs"]['model'][0] = pulid1_node_id
        elif len(face_image_filenames) == 2:
            workflow[first_block_node_id]["inputs"]['model'][0] = pulid2_node_id

        
        
        if face_node_ids:
            for i, face_filename in enumerate(face_image_filenames):
                face_load_node_id = face_node_ids.get(f"load_face_{i}")
                if face_load_node_id and face_load_node_id in workflow:
                    workflow[face_load_node_id]["inputs"]["image"] = face_filename
                    logger.info(f"人脸图像 {i+1} '{face_filename}' 已设置到加载节点 '{face_load_node_id}'")
                elif face_load_node_id:
                    logger.warning(f"文生图工作流 {workflow_json_path} 中未找到人脸图像加载节点 '{face_load_node_id}'. 人脸图像 {i+1} 可能不会生效。")
                else:
                    logger.warning(f"未配置人脸图像加载节点ID (T2I_FACE_NODE_IDS.load_face_{i})，人脸图像 {i+1} 将被忽略。")
        else:
            logger.warning("未配置人脸节点ID字典 (T2I_FACE_NODE_IDS)，所有人脸图像将被忽略。")
    else:
        workflow[first_block_node_id]["inputs"]['model'][0] = flux_forward_model_node_id

    return workflow
