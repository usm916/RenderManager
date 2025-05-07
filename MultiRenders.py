bl_info = {
    "name": "Multi Render Settings Manager",
    "author": "noTempo",
    "version": (1, 1),
    "blender": (2, 80, 0),
    "location": "Properties > Output Properties > Multi Render Settings",
    "description": "Manage multiple render settings profiles for CLI rendering",
    "category": "Render",
}

import bpy
import os
import platform
import re
import subprocess
import shlex
from bpy.props import (StringProperty, IntProperty, PointerProperty, 
                      CollectionProperty, IntProperty, BoolProperty)

# 個々のレンダリング設定項目
class RenderSettingsItem(bpy.types.PropertyGroup):
    name: StringProperty(
        name="Name",
        description="Name of this render settings profile",
        default="New Profile"
    )
    
    is_enabled: BoolProperty(
        name="Enabled",
        description="Enable/disable this render profile",
        default=True
    )
    
    output_path: StringProperty(
        name="Output Path",
        description="Path for rendered frames (relative to blend file)",
        default="renders/",
        subtype='DIR_PATH'
    )
    
    start_frame: IntProperty(
        name="Start Frame",
        description="First frame to render",
        default=0,
        min=-1000
    )
    
    end_frame: IntProperty(
        name="End Frame",
        description="Last frame to render",
        default=250,
        min=-1000
    )
    
    camera_name: StringProperty(
        name="Camera Name",
        description="Name of the camera to use for rendering",
        default="Camera"
    )
    
    is_expanded: BoolProperty(
        name="Expanded",
        description="Whether this profile is expanded in the UI",
        default=False
    )

# 設定を保存するためのプロパティグループ
class RenderSettingsProperties(bpy.types.PropertyGroup):
    profiles: CollectionProperty(
        type=RenderSettingsItem,
        name="Render Profiles",
        description="Collection of render settings profiles"
    )
    
    active_profile_index: IntProperty(
        name="Active Profile Index",
        default=0
    )
    
    # 共通出力パスの設定
    common_output_path: StringProperty(
        name="Common Output Path",
        description="Base output path for all render profiles",
        default="//",
        subtype='DIR_PATH'
    )

# システムコンソールを表示/非表示切り替えるオペレータ
class RENDER_OT_toggle_system_console(bpy.types.Operator):
    bl_idname = "render.toggle_system_console"
    bl_label = "Toggle System Console"
    bl_description = "Toggle the system console window visibility"
    
    def execute(self, context):
        if platform.system() == "Windows":
            bpy.ops.wm.console_toggle()
            self.report({'INFO'}, "System console toggled")
        else:
            self.report({'WARNING'}, "Console toggle only supported on Windows")
        return {'FINISHED'}

# バッチファイルを書き出すオペレータ
class RENDER_OT_export_batch_file(bpy.types.Operator):
    bl_idname = "render.export_batch_file"
    bl_label = "Export Batch File"
    bl_description = "Export a batch file to render all enabled profiles using CLI"
    
    filepath: StringProperty(
        subtype='FILE_PATH',
    )
    
    @classmethod
    def poll(cls, context):
        settings = context.scene.multi_render_settings
        return len([p for p in settings.profiles if p.is_enabled]) > 0
    
    def execute(self, context):
        if not self.filepath:
            self.report({'ERROR'}, "No filepath specified")
            return {'CANCELLED'}
            
        settings = context.scene.multi_render_settings
        blend_filepath = bpy.data.filepath
        
        if not blend_filepath:
            self.report({'ERROR'}, "Save your .blend file first")
            return {'CANCELLED'}
            
        is_windows = platform.system() == "Windows"
        ext = ".bat" if is_windows else ".sh"
        
        # ファイル拡張子の確認と追加
        if not self.filepath.endswith(ext):
            self.filepath += ext
            
        # 有効なプロファイルをフィルタリング
        enabled_profiles = [(i, p) for i, p in enumerate(settings.profiles) if p.is_enabled]
        
        if not enabled_profiles:
            self.report({'ERROR'}, "No enabled profiles available")
            return {'CANCELLED'}
            
        with open(self.filepath, 'w', encoding='utf-8') as f:
            # Windows用のバッチファイルヘッダー
            if is_windows:
                f.write("@echo off\n")
                f.write("echo Batch rendering started\n")
                f.write("echo.\n\n")
            else:
                f.write("#!/bin/bash\n")
                f.write("echo \"Batch rendering started\"\n")
                f.write("echo\n\n")
            
            # Blenderパスの推測
            blender_path = "blender"  # デフォルトはPATHから
            if is_windows:
                f.write("REM Configure your Blender path here if needed\n")
                f.write("set BLENDER_PATH=blender\n\n")
                blender_path = "%BLENDER_PATH%"
            else:
                f.write("# Configure your Blender path here if needed\n")
                f.write("BLENDER_PATH=blender\n\n")
                blender_path = "$BLENDER_PATH"
            
            # 各プロファイルのコマンドを生成（有効なプロファイルのみ）
            for idx, (profile_idx, profile) in enumerate(enabled_profiles):
                common_path = settings.common_output_path
                profile_path = profile.output_path
                
                # 共通パスと相対パスを組み合わせる
                if common_path.startswith("//") and profile_path.startswith("//"):
                    # 両方が相対パスの場合、common_pathの「//」を削除してから結合
                    output_path = common_path[2:] + profile_path[2:]
                    # 先頭に「//」を付け直す
                    output_path = "//" + output_path
                else:
                    # どちらかが絶対パスの場合は単純に結合
                    output_path = os.path.join(common_path, 
                                 profile_path[2:] if profile_path.startswith("//") else profile_path)
                
                # コマンド生成
                cmd = f"{blender_path} -b \"{blend_filepath}\" -P \"{os.path.realpath(__file__)}\" "
                cmd += f"-o \"{output_path}\" -s {profile.start_frame} -e {profile.end_frame} "
                cmd += f"-- \"{profile.camera_name}\" {profile_idx}"
                
                # バッチファイルに書き込み
                if is_windows:
                    f.write(f"echo Rendering profile {idx+1}/{len(enabled_profiles)}: {profile.name}\n")
                    f.write(f"{cmd}\n")
                    f.write("echo.\n\n")
                else:
                    f.write(f"echo \"Rendering profile {idx+1}/{len(enabled_profiles)}: {profile.name}\"\n")
                    f.write(f"{cmd}\n")
                    f.write("echo\n\n")
            
            # バッチファイルフッター
            if is_windows:
                f.write("echo All rendering tasks completed\n")
                f.write("pause\n")
            else:
                f.write("echo \"All rendering tasks completed\"\n")
                f.write("read -p \"Press Enter to continue...\"\n")
        
        # シェルスクリプトに実行権限を付与
        if not is_windows:
            try:
                os.chmod(self.filepath, 0o755)
            except:
                self.report({'WARNING'}, "Could not set executable permissions on the shell script")
        
        total_enabled = len(enabled_profiles)
        self.report({'INFO'}, f"Batch file with {total_enabled} enabled profiles exported to {self.filepath}")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # デフォルトのファイル名とパスを設定
        blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        default_filename = f"{blend_name}_render" + (".bat" if platform.system() == "Windows" else ".sh")
        
        if bpy.data.filepath:
            self.filepath = os.path.join(os.path.dirname(bpy.data.filepath), default_filename)
        else:
            self.filepath = default_filename
            
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# Add this new operator for the MP4 conversion
class RENDER_OT_convert_to_mp4(bpy.types.Operator):
    bl_idname = "render.convert_to_mp4"
    bl_label = "Convert Image Sequence to MP4"
    bl_description = "Convert image sequence in the output folder of the selected profile to MP4"
    
    @classmethod
    def poll(cls, context):
        settings = context.scene.multi_render_settings
        return len(settings.profiles) > 0 and settings.active_profile_index < len(settings.profiles)
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        profile = settings.profiles[settings.active_profile_index]
        
        # 出力パスの取得
        common_path = settings.common_output_path
        profile_path = profile.output_path
        
        # 共通パスを絶対パスに変換
        if common_path.startswith("//"):
            common_abs_path = bpy.path.abspath(common_path)
        else:
            common_abs_path = common_path
            
        # デバッグ情報
        self.report({'INFO'}, f"共通パス: {common_path} -> 絶対パス: {common_abs_path}")
        
        # プロファイルパスの処理
        if profile_path.startswith("//"):
            profile_rel_path = profile_path[2:]
            output_path = os.path.join(common_abs_path, profile_rel_path)
        elif profile_path.startswith("/"):
            profile_rel_path = profile_path[1:]
            output_path = os.path.join(common_abs_path, profile_rel_path)
        elif os.path.isabs(profile_path):
            output_path = profile_path
        else:
            output_path = os.path.join(common_abs_path, profile_path)
        
        # デバッグ情報
        self.report({'INFO'}, f"プロファイルパス: {profile_path} -> 最終出力パス: {output_path}")
        
        # フレーム番号プレースホルダーパターンを除去して出力ディレクトリとファイル名の基本部分を取得
        # ####パターンを検出
        pattern_match = re.search(r'#+', output_path)
        if pattern_match:
            # ####の連続の長さを取得（何桁の数字か）
            num_digits = len(pattern_match.group(0))
            # ####パターンの前のファイル名部分
            output_path_prefix = output_path[:pattern_match.start()]
            # ####パターンの後のファイル名部分（拡張子など）
            output_path_suffix = output_path[pattern_match.end():]
        else:
            # ####パターンがなければ、ファイル名の前に%04dを追加する想定
            output_path_prefix = output_path
            output_path_suffix = ""
            num_digits = 4  # デフォルトで4桁
        
        # 出力ディレクトリとファイル名ベースを取得
        output_dir = os.path.dirname(output_path_prefix)
        filename_base = os.path.basename(output_path_prefix)
        
        # 出力ディレクトリが存在するか確認し、なければ作成
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                self.report({'INFO'}, f"出力ディレクトリを作成しました: {output_dir}")
            except Exception as e:
                self.report({'ERROR'}, f"ディレクトリ作成に失敗しました: {str(e)}")
                return {'CANCELLED'}
        
        # レンダリング設定からファイル形式を取得
        file_format = context.scene.render.image_settings.file_format.lower()
        
        # 一般的な画像ファイル拡張子の対応表
        format_extensions = {
            'png': 'png',
            'jpeg': 'jpg',
            'tiff': 'tif',
            'open_exr': 'exr',
            'targa': 'tga',
            'bmp': 'bmp'
        }
        
        # ファイル拡張子を取得
        extension = format_extensions.get(file_format, 'png')
        
        # 拡張子がすでに指定されているか確認
        if not output_path_suffix and '.' not in filename_base:
            output_path_suffix = f".{extension}"
        
        # フォルダ内の画像ファイルを検索
        import glob
        # 検索パターン（ワイルドカード）
        search_pattern = os.path.join(output_dir, f"{filename_base}*{output_path_suffix}")
        self.report({'INFO'}, f"検索パターン: {search_pattern}")
        files = sorted(glob.glob(search_pattern))
        
        if not files:
            # 代替検索パターン
            search_pattern = os.path.join(output_dir, f"*.{extension}")
            self.report({'INFO'}, f"代替検索パターン: {search_pattern}")
            files = sorted(glob.glob(search_pattern))
            if not files:
                self.report({'ERROR'}, f"変換する画像ファイルが見つかりません: {search_pattern}")
                return {'CANCELLED'}
        
        self.report({'INFO'}, f"変換対象: {len(files)}ファイル")
        
        # 最初のファイルから連番パターンを抽出
        first_file = files[0]
        self.report({'INFO'}, f"最初のファイル: {first_file}")
        
        # ファイル名から数字部分を抽出して、FFmpegの%d形式に変換
        file_basename = os.path.basename(first_file)
        # 数字部分を抽出
        match = re.search(r'(\d+)', file_basename)
        if match:
            # 見つかった数字の位置
            num_pos = match.start()
            # 数字の長さ
            num_length = len(match.group(1))
            # 最初の番号
            start_num = int(match.group(1))
            
            # FFmpegの入力パターン（%04d形式）を構築
            input_prefix = os.path.join(output_dir, file_basename[:num_pos])
            input_suffix = file_basename[num_pos + num_length:]
            ffmpeg_input = f"{input_prefix}%0{num_length}d{input_suffix}"
            
            self.report({'INFO'}, f"FFmpeg入力パターン: {ffmpeg_input}, 開始番号: {start_num}")
        else:
            # 数字部分が見つからない場合は、単一ファイルとして処理
            self.report({'WARNING'}, "ファイル名に連番が見つかりません。単一ファイルとして処理します。")
            ffmpeg_input = first_file
            start_num = 1
        
        # MP4出力ファイル名を共通パスに設定
        # プロファイルのパス構造を反映したファイル名を作成
        if profile_path.startswith("//") or profile_path.startswith("/"):
            # 相対パスの場合、ディレクトリ構造を取得
            if profile_path.startswith("//"):
                dir_structure = profile_path[2:]
            else:
                dir_structure = profile_path[1:]
                
            # ディレクトリ区切り文字をアンダースコアに置換
            dir_structure = dir_structure.replace('/', '_').replace('\\', '_')
            
            # ####などの連番部分を除去
            dir_structure = re.sub(r'#*', '', dir_structure)
            
            # ファイル名をプロファイル名+ディレクトリ構造で作成
            mp4_filename = f"{profile.name}_{dir_structure}.mp4"
        else:
            # 絶対パスの場合はプロファイル名のみ
            mp4_filename = f"{profile.name}.mp4"
        
        # 特殊文字をアンダースコアに置換して安全なファイル名にする
        mp4_filename = re.sub(r'[<>:"/\\|?*]', '_', mp4_filename)
        
        # 共通パスにMP4ファイルを出力
        mp4_output = os.path.join(common_abs_path, mp4_filename)
        
        # MP4出力先ディレクトリの存在確認と作成
        mp4_output_dir = os.path.dirname(mp4_output)
        if not os.path.exists(mp4_output_dir):
            try:
                os.makedirs(mp4_output_dir, exist_ok=True)
                self.report({'INFO'}, f"MP4出力ディレクトリを作成しました: {mp4_output_dir}")
            except Exception as e:
                self.report({'ERROR'}, f"MP4出力ディレクトリ作成に失敗しました: {str(e)}")
                return {'CANCELLED'}
        
        # FFmpegのパスを取得
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            self.report({'ERROR'}, "FFmpegが見つかりません")
            return {'CANCELLED'}
        
        # フレームレートを取得
        fps = context.scene.render.fps / context.scene.render.fps_base
        
        # FFmpegコマンドの構築 - alpha_modeを削除
        if extension == 'exr':
            cmd = [
                ffmpeg_path,
                '-framerate', str(fps),
                '-start_number', str(start_num),
                '-i', ffmpeg_input,
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', '18',
                '-preset', 'slow',
                '-colorspace', 'bt709',
                '-y',
                mp4_output
            ]
        else:
            cmd = [
                ffmpeg_path,
                '-framerate', str(fps),
                '-start_number', str(start_num),
                '-i', ffmpeg_input,
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-vf', 'format=yuv420p',
                '-crf', '23',
                '-preset', 'medium',
                '-y',
                mp4_output
            ]

        try:
            # コマンド実行
            cmd_str = ' '.join(cmd)
            self.report({'INFO'}, f"FFmpegコマンド: {cmd_str}")
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.report({'ERROR'}, f"MP4変換に失敗しました: {stderr}")
                return {'CANCELLED'}
            
            self.report({'INFO'}, f"MP4ファイルが作成されました: {mp4_output}")
            return {'FINISHED'}
        
        except Exception as e:
            self.report({'ERROR'}, f"エラーが発生しました: {str(e)}")
            return {'CANCELLED'}
    
    def get_ffmpeg_path(self):
        """FFmpegのパスを取得する"""
        # Blender同梱のFFmpegパスを探す
        blender_bin = bpy.app.binary_path
        blender_dir = os.path.dirname(blender_bin)
        
        # 潜在的なFFmpegのパス
        possible_paths = [
            # Windows
            os.path.join(blender_dir, 'ffmpeg.exe'),
            # macOS
            os.path.join(os.path.dirname(blender_dir), 'Resources', 'ffmpeg'),
            # Linux
            os.path.join(blender_dir, 'ffmpeg'),
            # システムパス上のFFmpeg
            'ffmpeg'
        ]
        
        # 存在するパスを返す
        for path in possible_paths:
            if os.path.exists(path) or path == 'ffmpeg':
                return path
        
        return None

# UI パネル
# Multi Render Settings Managerパネル
class RENDER_PT_multi_settings_manager(bpy.types.Panel):
    bl_label = "Multi Render Settings Manager"
    bl_idname = "RENDER_PT_multi_settings_manager"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.multi_render_settings
        
        # "Render All Profiles" button at the top with conditional enabling
        row = layout.row()
        if len(settings.profiles) > 0:
            row.operator("render.render_all_profiles", icon='RENDER_ANIMATION')
        else:
            row.operator("render.render_all_profiles", icon='RENDER_ANIMATION', text="Render All Profiles (No Profiles)")
            row.enabled = False
        
        # システムコンソールボタンとバッチファイル生成ボタン
        row = layout.row()
        row.operator("render.toggle_system_console", icon='CONSOLE')
        row.operator("render.export_batch_file", icon='FILE_SCRIPT')
        
                # 共通出力パス設定
        layout.separator()
        box = layout.box()
        box.label(text="Common Settings:")
        
        # MP4変換ボタンを追加
        if len(settings.profiles) > 0:
            box.operator("render.convert_to_mp4", icon='SEQUENCE')
        else:
            row = box.row()
            row.operator("render.convert_to_mp4", icon='SEQUENCE')
            row.enabled = False
        
        box.prop(settings, "common_output_path")

        # 共通出力パス設定
        layout.separator()
        box = layout.box()
        box.label(text="Common Settings:")
        box.prop(settings, "common_output_path")
        
        # プロファイル管理
        layout.separator()
        row = layout.row()
        row.template_list("RENDER_UL_profiles", "", settings, "profiles",
                          settings, "active_profile_index", rows=3)
        
        col = row.column(align=True)
        col.operator("render.add_profile", icon='ADD', text="")
        col.operator("render.remove_profile", icon='REMOVE', text="")
        col.separator()
        col.operator("render.move_profile_up", icon='TRIA_UP', text="")
        col.operator("render.move_profile_down", icon='TRIA_DOWN', text="")
        
        # 選択されたプロファイルの詳細表示
        if len(settings.profiles) > 0 and settings.active_profile_index < len(settings.profiles):
            profile = settings.profiles[settings.active_profile_index]
            
            layout.separator()
            box = layout.box()
            
            # タイトル行：名前、Set ボタン、展開トグル
            row = box.row()
            name_row = row.row()
            name_row.prop(profile, "Prof name")
            
            # 右側にSetボタンとexpandトグルを配置
            buttons_row = row.row(align=True)
            # "Set As Active Camera"ボタンを"Set"という短い名前に変更して配置
            op = buttons_row.operator("render.set_active_camera_from_profile", text="set as Active", icon='CAMERA_DATA')
            op.profile_index = settings.active_profile_index
            # 展開ボタン
            buttons_row.prop(profile, "is_expanded", icon='DOWNARROW_HLT' if profile.is_expanded else 'RIGHTARROW', emboss=False)
            
            if profile.is_expanded:
                # 出力パス設定
                box.prop(profile, "output_path")
                
                # フレーム範囲設定
                row = box.row()
                row.prop(profile, "start_frame")
                row.prop(profile, "end_frame")
                
                # カメラ設定
                box.prop_search(profile, "camera_name", bpy.data, "objects", text="Camera")
                
                # カメラの情報表示
                cameras = [obj.name for obj in bpy.data.objects if obj.type == 'CAMERA']
                if profile.camera_name in cameras:
                    box.label(text=f"Camera valid: {profile.camera_name}", icon='CHECKMARK')
                else:
                    box.label(text="Warning: Selected camera not found!", icon='ERROR')
                
                # レンダリングボタン
                box.operator("render.render_with_profile", text="Render this camera").profile_index = settings.active_profile_index
            
            # 完全パスの表示
            full_path = os.path.join(settings.common_output_path,
                                  profile.output_path[2:] if profile.output_path.startswith("//") else profile.output_path)
            full_path = full_path.replace("\\", "/")
            
            box = layout.box()
            box.label(text="Full Output Path:")
            box.label(text=full_path)
            
            # コマンドライン表示を改行して完全表示
            cmd_box = layout.box()
            cmd_box.label(text="CLI Command:")
            
            # コマンドを複数行に分けて表示
            cmd = f"blender -b \"{bpy.data.filepath}\""
            cmd_box.label(text=cmd)
            
            cmd = f"-P \"{os.path.realpath(__file__)}\""
            cmd_box.label(text=cmd)
            
            cmd = f"-o \"{full_path}\""
            cmd_box.label(text=cmd)
            
            cmd = f"-s {profile.start_frame} -e {profile.end_frame}"
            cmd_box.label(text=cmd)
            
            cmd = f"-- \"{profile.camera_name}\" {settings.active_profile_index}"
            cmd_box.label(text=cmd)
            
            # 1行で表示するバージョンも維持（コピー用）
            full_cmd = f"blender -b \"{bpy.data.filepath}\" -P \"{os.path.realpath(__file__)}\" "
            full_cmd += f"-o \"{full_path}\" -s {profile.start_frame} -e {profile.end_frame} "
            full_cmd += f"-- \"{profile.camera_name}\" {settings.active_profile_index}"
            
            # コピーしやすいようにテキストボックスとして表示
            cmd_box.separator()
            cmd_box.label(text="Full command (for copy):")
            row = cmd_box.row()
            row.scale_y = 0.6
            row.label(text=full_cmd, translate=False)


# プロファイルのリスト表示用UIリスト
class RENDER_UL_profiles(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            # 有効/無効トグルボタン
            row = layout.row(align=True)
            row.prop(item, "is_enabled", text="")  # チェックボックスとして表示
            
            # 名前と情報
            name_row = row.row()
            if not item.is_enabled:
                name_row.enabled = False
            name_row.label(text=item.name)
            
            # フレーム範囲とカメラ情報
            info_row = row.row()
            if not item.is_enabled:
                info_row.enabled = False
            info_row.label(text=f"Frames: {item.start_frame}-{item.end_frame}")
            info_row.label(text=f"Camera: {item.camera_name}")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.name)
            layout.prop(item, "is_enabled", text="")

# プロファイル追加オペレータ
class RENDER_OT_add_profile(bpy.types.Operator):
    bl_idname = "render.add_profile"
    bl_label = "Add Render Profile"
    bl_description = "Add a new render settings profile"
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        profile = settings.profiles.add()
        profile.name = f"Profile {len(settings.profiles)}"
        settings.active_profile_index = len(settings.profiles) - 1
        return {'FINISHED'}

# プロファイル削除オペレータ
class RENDER_OT_remove_profile(bpy.types.Operator):
    bl_idname = "render.remove_profile"
    bl_label = "Remove Render Profile"
    bl_description = "Remove the selected render settings profile"
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        if len(settings.profiles) > 0:
            settings.profiles.remove(settings.active_profile_index)
            settings.active_profile_index = max(0, min(settings.active_profile_index, len(settings.profiles) - 1))
        return {'FINISHED'}

# プロファイルを上に移動
class RENDER_OT_move_profile_up(bpy.types.Operator):
    bl_idname = "render.move_profile_up"
    bl_label = "Move Profile Up"
    bl_description = "Move the selected profile up in the list"
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        if settings.active_profile_index > 0:
            settings.profiles.move(settings.active_profile_index, settings.active_profile_index - 1)
            settings.active_profile_index -= 1
        return {'FINISHED'}

# プロファイルを下に移動
class RENDER_OT_move_profile_down(bpy.types.Operator):
    bl_idname = "render.move_profile_down"
    bl_label = "Move Profile Down"
    bl_description = "Move the selected profile down in the list"
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        if 0 <= settings.active_profile_index < len(settings.profiles) - 1:
            settings.profiles.move(settings.active_profile_index, settings.active_profile_index + 1)
            settings.active_profile_index += 1
        return {'FINISHED'}

# 現在のカメラを設定するオペレータ
class RENDER_OT_set_active_camera_from_profile(bpy.types.Operator):
    bl_idname = "render.set_active_camera_from_profile"
    bl_label = "Set As Active Camera"
    bl_description = "Set the camera from this profile as the active camera"
    
    profile_index: IntProperty()
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        profile = settings.profiles[self.profile_index]
        camera_name = profile.camera_name
        
        if camera_name in bpy.data.objects and bpy.data.objects[camera_name].type == 'CAMERA':
            context.scene.camera = bpy.data.objects[camera_name]
            self.report({'INFO'}, f"Camera set to {camera_name}")
        else:
            self.report({'ERROR'}, f"Camera {camera_name} not found!")
            
        return {'FINISHED'}

# プロファイルを使用してレンダリングするオペレータ
class RENDER_OT_render_with_profile(bpy.types.Operator):
    bl_idname = "render.render_with_profile"
    bl_label = "Render with Profile"
    bl_description = "Start rendering with this profile's settings"
    
    profile_index: IntProperty()
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        profile = settings.profiles[self.profile_index]
        
        # カメラ設定
        if profile.camera_name in bpy.data.objects and bpy.data.objects[profile.camera_name].type == 'CAMERA':
            context.scene.camera = bpy.data.objects[profile.camera_name]
        else:
            self.report({'ERROR'}, f"Camera {profile.camera_name} not found!")
            return {'CANCELLED'}
        
        # 元の設定を保存
        original_filepath = context.scene.render.filepath
        original_start = context.scene.frame_start
        original_end = context.scene.frame_end
        
        # 共通パスとプロファイルパスを結合
        common_path = settings.common_output_path
        profile_path = profile.output_path
        
        # 共通パスと相対パスを組み合わせる
        if common_path.startswith("//") and profile_path.startswith("//"):
            # 両方が相対パスの場合、common_pathの「//」を削除してから結合
            output_path = common_path[2:] + profile_path[2:]
            # 先頭に「//」を付け直す
            output_path = "//" + output_path
        else:
            # どちらかが絶対パスの場合は単純に結合
            output_path = os.path.join(common_path, 
                                     profile_path[2:] if profile_path.startswith("//") else profile_path)
        
        # 出力パス設定
        context.scene.render.filepath = output_path
        
        # フレーム範囲設定
        context.scene.frame_start = profile.start_frame
        context.scene.frame_end = profile.end_frame
        
        # レンダリング開始
        bpy.ops.render.render(animation=True)
        
        # 元の設定を復元
        context.scene.render.filepath = original_filepath
        context.scene.frame_start = original_start
        context.scene.frame_end = original_end
        
        return {'FINISHED'}

# 全てのプロファイルを連続してレンダリングするオペレータ
class RENDER_OT_render_all_profiles(bpy.types.Operator):
    bl_idname = "render.render_all_profiles"
    bl_label = "Render All Profiles"
    bl_description = "Render all enabled profiles in sequence"
    
    def execute(self, context):
        settings = context.scene.multi_render_settings
        
        # 有効なプロファイルをカウント
        enabled_profiles = [p for p in settings.profiles if p.is_enabled]
        if not enabled_profiles:
            self.report({'WARNING'}, "No enabled profiles available for rendering")
            return {'CANCELLED'}
        
        # 元の設定を保存
        original_filepath = context.scene.render.filepath
        original_start = context.scene.frame_start
        original_end = context.scene.frame_end
        original_camera = context.scene.camera
        
        # 有効なプロファイルのみレンダリング
        rendered_count = 0
        total_enabled = len(enabled_profiles)
        for i, profile in enumerate(settings.profiles):
            if not profile.is_enabled:
                continue
                
            rendered_count += 1
            self.report({'INFO'}, f"Rendering profile {rendered_count}/{total_enabled}: {profile.name}")
            
            # カメラ設定
            if profile.camera_name in bpy.data.objects and bpy.data.objects[profile.camera_name].type == 'CAMERA':
                context.scene.camera = bpy.data.objects[profile.camera_name]
            else:
                self.report({'WARNING'}, f"Camera {profile.camera_name} not found for profile {profile.name}, skipping")
                continue
            
            # 共通パスとプロファイルパスを結合
            common_path = settings.common_output_path
            profile_path = profile.output_path
            
            # 共通パスと相対パスを組み合わせる
            if common_path.startswith("//") and profile_path.startswith("//"):
                # 両方が相対パスの場合、common_pathの「//」を削除してから結合
                output_path = common_path[2:] + profile_path[2:]
                # 先頭に「//」を付け直す
                output_path = "//" + output_path
            else:
                # どちらかが絶対パスの場合は単純に結合
                output_path = os.path.join(common_path, 
                                     profile_path[2:] if profile_path.startswith("//") else profile_path)
            
            # 出力パス設定
            context.scene.render.filepath = output_path
            
            # フレーム範囲設定
            context.scene.frame_start = profile.start_frame
            context.scene.frame_end = profile.end_frame
            
            # レンダリング開始
            bpy.ops.render.render(animation=True)
        
        # 元の設定を復元
        context.scene.render.filepath = original_filepath
        context.scene.frame_start = original_start
        context.scene.frame_end = original_end
        context.scene.camera = original_camera
        
        self.report({'INFO'}, f"All {rendered_count} enabled profiles rendered successfully")
        return {'FINISHED'}

# 「すべてのプロファイルをレンダリング」ボタンを追加するサブパネル
class RENDER_PT_multi_settings_actions(bpy.types.Panel):
    bl_label = "Batch Actions"
    bl_idname = "RENDER_PT_multi_settings_actions"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    bl_parent_id = "RENDER_PT_multi_settings_manager"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.multi_render_settings
        
        if len(settings.profiles) > 0:
            layout.operator("render.render_all_profiles", icon='RENDER_ANIMATION')
        else:
            layout.label(text="No profiles available")

# コマンドラインからの実行をサポートする関数
def render_from_cli():
    import sys
    
    # バックグラウンドモードでは bpy.context.scene ではなく bpy.data.scenes[0] を使用
    scene = bpy.data.scenes[0]
    
    # プロファイルインデックスを取得（--の後の2番目の引数）
    profile_index = 0
    if '--' in sys.argv:
        double_dash_idx = sys.argv.index('--')
        if double_dash_idx + 2 < len(sys.argv):
            try:
                profile_index = int(sys.argv[double_dash_idx + 2])
            except ValueError:
                print("Warning: Could not parse profile index, using first profile")
    
    # 引数を解析する関数
    def get_arg_value(arg_name):
        if arg_name in sys.argv:
            idx = sys.argv.index(arg_name)
            if idx + 1 < len(sys.argv):
                return sys.argv[idx + 1]
        return None
    
    # 出力パス、フレーム範囲などをCLIから優先的に取得
    output_path = get_arg_value('-o')
    start_frame = get_arg_value('-s')
    end_frame = get_arg_value('-e')
    camera_name = None
    if '--' in sys.argv:
        double_dash_idx = sys.argv.index('--')
        if double_dash_idx + 1 < len(sys.argv):
            camera_name = sys.argv[double_dash_idx + 1]
    
    # プロファイルの有効性チェック
    settings = scene.multi_render_settings
    if len(settings.profiles) == 0:
        print("No render profiles defined, cannot render")
        return
    
    if profile_index >= len(settings.profiles):
        print(f"Profile index {profile_index} is out of range, using first profile")
        profile_index = 0
    
    profile = settings.profiles[profile_index]
    print(f"Using profile: {profile.name}")
    
    # CLI引数を優先し、指定がなければプロファイルから取得
    # 共通パスとプロファイルパスを結合
    if not output_path:
        common_path = settings.common_output_path
        profile_path = profile.output_path
        
        # 共通パスと相対パスを組み合わせる
        if common_path.startswith("//") and profile_path.startswith("//"):
            # 両方が相対パスの場合、common_pathの「//」を削除してから結合
            output_path = common_path[2:] + profile_path[2:]
            # 先頭に「//」を付け直す
            output_path = "//" + output_path
        else:
            # どちらかが絶対パスの場合は単純に結合
            output_path = os.path.join(common_path, 
                                 profile_path[2:] if profile_path.startswith("//") else profile_path)
    
    final_start_frame = int(start_frame) if start_frame else profile.start_frame
    final_end_frame = int(end_frame) if end_frame else profile.end_frame
    final_camera_name = camera_name if camera_name else profile.camera_name
    
    # カメラ設定
    if final_camera_name in bpy.data.objects and bpy.data.objects[final_camera_name].type == 'CAMERA':
        scene.camera = bpy.data.objects[final_camera_name]
        print(f"Camera set to: {final_camera_name}")
    else:
        print(f"Camera '{final_camera_name}' not found or not a camera!")
        available_cameras = [obj.name for obj in bpy.data.objects if obj.type == 'CAMERA']
        print(f"Available cameras: {available_cameras}")
        if available_cameras:
            print(f"Using first available camera: {available_cameras[0]}")
            scene.camera = bpy.data.objects[available_cameras[0]]
        else:
            print("No camera found in the scene, cannot render")
            return
    
    # 出力パス設定
    scene.render.filepath = output_path
    print(f"Output path: {output_path}")
    
    # フレーム範囲設定
    scene.frame_start = final_start_frame
    scene.frame_end = final_end_frame
    print(f"Frame range: {final_start_frame} - {final_end_frame}")
    
    # レンダリング実行
    print("Starting render...")
    bpy.ops.render.render(animation=True)
    print("Render complete!")


# アドオンの登録関数
classes = (
    RenderSettingsItem,
    RenderSettingsProperties,
    RENDER_UL_profiles,
    RENDER_PT_multi_settings_manager,
    # RENDER_PT_multi_settings_actions,  # Remove this line as we no longer need this panel
    RENDER_OT_add_profile,
    RENDER_OT_remove_profile,
    RENDER_OT_move_profile_up,
    RENDER_OT_move_profile_down,
    RENDER_OT_set_active_camera_from_profile,
    RENDER_OT_render_with_profile,
    RENDER_OT_render_all_profiles,
    RENDER_OT_toggle_system_console,
    RENDER_OT_export_batch_file,
    RENDER_OT_convert_to_mp4,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # シーンにプロパティを追加
    bpy.types.Scene.multi_render_settings = PointerProperty(type=RenderSettingsProperties)
    
    # コマンドラインから実行された場合
    if bpy.app.background:
        # セットアップが完了するまで少し待機
        import time
        time.sleep(0.5)
        # 別の方法でCLI実行を処理
        try:
            render_from_cli()
        except Exception as e:
            print(f"Error during CLI rendering: {e}")

def unregister():
    # コマンドラインから実行した場合は何もしない
    if bpy.app.background:
        return
        
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.multi_render_settings

# スクリプトとして実行された場合（CLIから）
if __name__ == "__main__":
    register()
