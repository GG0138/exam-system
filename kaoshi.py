import streamlit as st
import pandas as pd
import re
import os
import json
import pickle
import hashlib
from datetime import datetime
from difflib import SequenceMatcher
import warnings
import random

warnings.filterwarnings('ignore')

st.set_page_config(page_title="智能考试系统", page_icon="📚", layout="wide")
st.title("📚 智能考试系统（优化版）")


# ================== 工具函数：错题管理 ==================
def get_wrong_questions_filename(exam_id):
    """获取错题本文件名"""
    wrong_dir = "wrong_questions"
    if not os.path.exists(wrong_dir):
        os.makedirs(wrong_dir)
    exam_hash = hashlib.md5(exam_id.encode()).hexdigest()[:8]
    return os.path.join(wrong_dir, f"wrong_{exam_hash}.pkl")


def save_wrong_question(exam_id, question_data, user_answer, is_correct):
    """保存错题"""
    try:
        filename = get_wrong_questions_filename(exam_id)
        wrong_questions = load_wrong_questions(exam_id)

        question_id = f"{question_data.get('source', '')}_{question_data.get('row_index', 0)}"

        # 更新或添加错题
        exists = False
        for i, wq in enumerate(wrong_questions):
            if wq.get('question_id') == question_id:
                wrong_questions[i].update({
                    'user_answer': user_answer,
                    'is_correct': is_correct,
                    'last_attempt': datetime.now().isoformat(),
                    'attempt_count': wq.get('attempt_count', 0) + 1,
                    'last_correct': is_correct
                })
                exists = True
                break

        if not exists and not is_correct:  # 只保存错误的题目
            wrong_question = {
                'question_id': question_id,
                'question': question_data.get('question', ''),
                'question_type': question_data.get('type', ''),
                'correct_answer': question_data.get('correct_answer_display', ''),
                'correct_answer_normalized': question_data.get('correct_answer_normalized', ''),
                'options': question_data.get('options', []),
                'user_answer': user_answer,
                'explanation': question_data.get('explanation', ''),
                'source': question_data.get('source', ''),
                'first_wrong': datetime.now().isoformat(),
                'last_attempt': datetime.now().isoformat(),
                'attempt_count': 1,
                'reviewed': False,
                'last_correct': False
            }
            wrong_questions.append(wrong_question)

        with open(filename, 'wb') as f:
            pickle.dump(wrong_questions, f)
        return True
    except Exception as e:
        st.error(f"保存错题失败: {e}")
        return False


def load_wrong_questions(exam_id):
    """加载错题"""
    try:
        filename = get_wrong_questions_filename(exam_id)
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                return pickle.load(f)
    except:
        pass
    return []


def get_wrong_stats(exam_id):
    """获取错题统计"""
    wrong_questions = load_wrong_questions(exam_id)
    total = len(wrong_questions)
    not_reviewed = len([wq for wq in wrong_questions if not wq.get('reviewed', False)])
    return {'total': total, 'not_reviewed': not_reviewed}


def update_wrong_question_status(exam_id, question_id, reviewed=True):
    """更新错题状态"""
    try:
        filename = get_wrong_questions_filename(exam_id)
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                wrong_questions = pickle.load(f)

            for wq in wrong_questions:
                if wq.get('question_id') == question_id:
                    wq['reviewed'] = reviewed
                    break

            with open(filename, 'wb') as f:
                pickle.dump(wrong_questions, f)
            return True
    except:
        pass
    return False


def reset_wrong_question_session_state():
    """重置错题本的会话状态"""
    keys_to_reset = []
    for key in st.session_state.keys():
        if key.startswith("wrong_") and key not in ["wrong_questions_list", "wrong_question_index"]:
            keys_to_reset.append(key)

    for key in keys_to_reset:
        del st.session_state[key]


# ================== 工具函数：进度保存/加载 ==================
def get_progress_filename(exam_id):
    """生成进度文件名"""
    progress_dir = "progress_data"
    if not os.path.exists(progress_dir):
        os.makedirs(progress_dir)
    exam_hash = hashlib.md5(exam_id.encode()).hexdigest()[:8]
    return os.path.join(progress_dir, f"progress_{exam_hash}.pkl")


def save_progress(exam_id, progress_data, config_data=None, extra_data=None):
    """保存进度到文件"""
    try:
        filename = get_progress_filename(exam_id)
        data = {
            "progress": progress_data,
            "config": config_data or {},
            "extra": extra_data or {},
            "timestamp": datetime.now().isoformat()
        }
        with open(filename, 'wb') as f:
            pickle.dump(data, f)
        return True
    except Exception as e:
        st.error(f"保存进度失败: {e}")
        return False


def load_progress(exam_id):
    """从文件加载进度"""
    try:
        filename = get_progress_filename(exam_id)
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                data = pickle.load(f)
            if "timestamp" in data:
                file_time = datetime.fromisoformat(data["timestamp"])
                if (datetime.now() - file_time).days > 30:  # 30天后自动过期
                    return {}, {}, {}
            return data.get("progress", {}), data.get("config", {}), data.get("extra", {})
    except Exception as e:
        st.error(f"加载进度失败: {e}")
    return {}, {}, {}


def clear_progress(exam_id):
    """清除进度文件"""
    try:
        filename = get_progress_filename(exam_id)
        if os.path.exists(filename):
            os.remove(filename)
            return True
    except:
        pass
    return False


# ================== 判分函数 ==================
def normalize_answer(answer):
    """标准化答案字符串"""
    if not answer or pd.isna(answer):
        return ""

    answer = str(answer).strip()
    if not answer:
        return ""

    # 转换为小写进行比较
    answer_lower = answer.lower()

    # 判断题标准化
    if answer_lower in ["✅", "对", "正确", "√", "✓", "true", "t", "是", "yes", "y", "1", "正确", "对的"]:
        return "对"
    elif answer_lower in ["❌", "错", "错误", "×", "✗", "false", "f", "否", "no", "n", "0", "错误", "错的"]:
        return "错"

    # 选择题标准化（提取选项字母）
    match = re.match(r'^[\(（\s]*([A-Da-d])[\)）\s]*[\.．、:：]?\s*', answer)
    if match:
        return match.group(1).upper()

    return answer.strip()


def check_answer(user_input, question):
    """判分函数 - 修复版"""
    if not user_input or str(user_input).strip() == "":
        return False

    user_input = str(user_input).strip()
    correct_disp = str(question["correct_answer_display"]).strip()
    q_type = question["type"]

    # 标准化答案
    user_norm = normalize_answer(user_input)
    correct_norm = normalize_answer(correct_disp)

    if q_type == "判断":
        return user_norm == correct_norm

    elif q_type == "单选":
        # 提取用户答案中的选项标签
        user_match = re.match(r'^[\(（\s]*([A-Da-d])[\)）\s]*[\.．、:：]?\s*', user_input)

        if user_match and correct_norm and len(correct_norm) == 1 and correct_norm.isalpha():
            # 比较选项字母
            return user_match.group(1).upper() == correct_norm.upper()
        else:
            # 直接比较标准化后的答案
            return user_norm == correct_norm

    elif q_type == "填空":
        # 填空题直接比较标准化后的答案
        return user_norm == correct_norm

    elif q_type == "简答":
        # 简答题相似度判断
        def clean_text(text):
            if not text:
                return ""
            # 移除标点符号和空格
            text = re.sub(r'[\s\p{P}\p{S}]+', '', text, flags=re.UNICODE)
            return text.lower()

        user_clean = clean_text(user_input)
        correct_clean = clean_text(correct_disp)

        if len(correct_clean) == 0:
            return False

        similarity = SequenceMatcher(None, user_clean, correct_clean).ratio()
        return similarity >= 0.7

    return False


# ================== 初始化状态 ==================
if "available_exam_files" not in st.session_state:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, "data")
    xlsx_files = []
    if os.path.exists(data_dir):
        xlsx_files = [f for f in os.listdir(data_dir) if f.endswith(".xlsx")]
    if not xlsx_files:
        xlsx_files = [f for f in os.listdir(".") if f.endswith(".xlsx")]
    st.session_state.available_exam_files = sorted(xlsx_files)

# 初始化其他状态变量
state_defaults = [
    ("selected_exam_file", None),
    ("all_questions", []),
    ("filtered_questions", []),
    ("current_index", 0),
    ("user_progress", {}),
    ("exam_config", {}),
    ("exam_started", False),
    ("show_answer", {}),
    ("answer_submitted", {}),
    ("detection_stats", {}),
    ("enhanced_loading", False),
    ("question_selection_mode", False),
    ("selected_question_indices", []),
    ("view_wrong_questions", False),
    ("wrong_questions_list", []),
    ("wrong_question_index", 0)
]

for key, default in state_defaults:
    if key not in st.session_state:
        st.session_state[key] = default


# ================== 题型识别函数 ==================
def intelligent_detect_question_type(question_text, correct_answer, options_text, explicit_type=None):
    """
    智能识别题目类型 - 修复版
    """
    # 如果Excel中明确指定了题型，优先使用
    if explicit_type and str(explicit_type).strip() in ["判断", "单选", "填空", "简答", "多选"]:
        return str(explicit_type).strip()

    # 标准化输入
    question_text = str(question_text).strip() if question_text else ""
    correct_answer = str(correct_answer).strip() if correct_answer else ""
    options_text = str(options_text).strip() if options_text else ""

    # 1. 判断题识别
    def is_judgment_question(q_text, ans):
        """判断是否为判断题"""
        # 答案特征
        judgment_answers = {
            "对": ["对", "正确", "√", "✓", "✅", "是", "yes", "true", "True", "T", "t"],
            "错": ["错", "错误", "×", "✗", "❌", "否", "no", "false", "False", "F", "f"]
        }

        # 检查答案格式
        ans_lower = str(ans).lower().strip()
        for key, patterns in judgment_answers.items():
            if ans_lower in patterns or ans in patterns:
                # 检查题目特征
                q_lower = q_text.lower()
                judgment_keywords = [
                    "是否正确", "是对是错", "判断正误", "判断对错", "下列说法是否正确",
                    "请判断", "是否正确", "true or false", "判断下列说法", "正误"
                ]
                has_judgment_keyword = any(keyword in q_lower for keyword in judgment_keywords)

                if has_judgment_keyword or not options_text or len(options_text) < 20:
                    return key
        return None

    judgment_type = is_judgment_question(question_text, correct_answer)
    if judgment_type:
        return "判断"

    # 2. 选择题识别
    answer_is_option = re.match(r'^[A-Da-d]$', str(correct_answer).strip()) is not None

    # 检查选项文本是否包含选择题模式
    choice_patterns = [
        r'[A-Da-d][\.．、:：]\s*[^\s]+',
        r'选项[ABCDabcd][\.．、:：]?\s*[^\s]+',
        r'[①②③④][\.．、:：]\s*[^\s]+',
        r'[1-4][\.．、:：]\s*[^\s]+',
    ]

    has_choice_pattern = False
    option_count = 0
    for pattern in choice_patterns:
        matches = re.findall(pattern, options_text)
        if len(matches) >= 2:
            has_choice_pattern = True
            option_count = len(matches)
            break

    # 检查题目是否包含选择题特征
    question_lower = question_text.lower()
    choice_keywords = ["下列", "选择", "哪", "哪些", "正确的是", "不正确的是", "选项", "最符合"]
    has_choice_keyword = any(keyword in question_lower for keyword in choice_keywords)

    # 特别处理以括号结束的题目
    has_blank_at_end = re.search(r'（\s*）\s*[。.]?$', question_text) is not None
    has_parentheses_at_end = re.search(r'\(\s*\)\s*[.。]?$', question_text) is not None

    # 选择题识别条件
    if answer_is_option and (has_choice_pattern or has_choice_keyword or has_blank_at_end or has_parentheses_at_end):
        if option_count >= 2:
            return "单选"

    # 3. 填空题识别
    blank_patterns = [
        r'_{2,}', r'\(\)', r'（\s*）', r'【\s*】', r'______', r'……', r'---',
    ]
    has_blank = any(re.search(pattern, question_text) for pattern in blank_patterns)

    fill_keywords = ["填空", "填写", "填入", "补充", "补全"]
    has_fill_keyword = any(keyword in question_text for keyword in fill_keywords)

    is_short_answer = 1 <= len(str(correct_answer).strip()) <= 30

    if has_blank or has_fill_keyword or is_short_answer:
        return "填空"

    # 4. 简答题识别
    essay_keywords = ["简述", "论述", "说明", "阐述", "分析", "解释", "为什么", "如何", "怎样", "什么", "意义"]
    has_essay_keyword = any(keyword in question_text for keyword in essay_keywords)

    is_long_answer = len(str(correct_answer).strip()) > 30

    if has_essay_keyword or is_long_answer:
        return "简答"

    # 5. 默认判断
    if answer_is_option and option_count >= 2:
        return "单选"
    elif is_short_answer:
        return "填空"
    else:
        return "简答"


def parse_options_from_cell(cell_content):
    """从一个单元格中解析出选项（支持多种格式）"""
    options = []

    if not cell_content or pd.isna(cell_content) or str(cell_content).strip() == "":
        return options

    content = str(cell_content).strip()

    # 尝试用换行符分割
    lines = content.split('\n')

    # 如果只有一个元素，尝试用分号或中文分号分割
    if len(lines) == 1:
        if ';' in content:
            lines = content.split(';')
        elif '；' in content:
            lines = content.split('；')
        elif '，' in content:
            lines = content.split('，')
        elif ',' in content:
            lines = content.split(',')

    # 清理每行
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line:
            cleaned_lines.append(line)

    # 为每行分配标签
    for i, line in enumerate(cleaned_lines):
        if i >= 4:  # 最多处理4个选项
            break

        # 常见的选项标签
        label_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
        label = label_map.get(i, '')

        # 检查行是否已经包含标签
        match = re.match(r'^([A-Da-d])[\.．、:：]\s*(.*)', line)
        if match:
            label = match.group(1).upper()
            text = match.group(2).strip()
        else:
            match = re.match(r'^选项([A-Da-d])[\.．、:：]?\s*(.*)', line)
            if match:
                label = match.group(1).upper()
                text = match.group(2).strip()
            else:
                match = re.match(r'^([①②③④])[\.．、:：]\s*(.*)', line)
                if match:
                    # 将中文数字转换为字母
                    chinese_to_letter = {'①': 'A', '②': 'B', '③': 'C', '④': 'D'}
                    label = chinese_to_letter.get(match.group(1), label)
                    text = match.group(2).strip()
                else:
                    match = re.match(r'^([1-4])[\.．、:：]\s*(.*)', line)
                    if match:
                        # 将数字转换为字母
                        num_to_letter = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}
                        label = num_to_letter.get(match.group(1), label)
                        text = match.group(2).strip()
                    else:
                        # 如果没有匹配到标签格式，使用分配的标签
                        text = line

        # 如果已经存在该标签的选项，跳过
        if any(opt['label'] == label for opt in options):
            continue

        options.append({'label': label, 'text': text})

    return options


# ================== 题库加载函数 ==================
@st.cache_resource
def load_questions_with_intelligent_detection(file_path):
    """智能题型识别题库加载函数 - 修复单元格选项解析"""
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            # 尝试在data目录下查找
            data_path = os.path.join("data", file_path)
            if os.path.exists(data_path):
                file_path = data_path
            else:
                # 尝试在当前目录下直接查找
                current_dir = os.path.dirname(os.path.abspath(__file__))
                abs_path = os.path.join(current_dir, file_path)
                if os.path.exists(abs_path):
                    file_path = abs_path
                else:
                    st.error(f"❌ 找不到题库文件: {file_path}")
                    return [], {}

        st.info(f"正在加载文件: {file_path}")

        try:
            sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')
        except Exception as e:
            st.error(f"读取Excel文件失败: {e}")
            return [], {}

        if not sheets:
            st.error("❌ Excel文件为空或格式不正确")
            return [], {}

        all_questions = []
        detection_stats = {}

        for sheet_name, df in sheets.items():
            if df.empty:
                continue

            # 查找题目列和答案列
            question_col = None
            answer_col = None

            # 先尝试查找标准列名
            for col in df.columns:
                col_str = str(col).strip()
                if col_str == "题目" or col_str == "question":
                    question_col = col
                elif col_str == "正确答案" or col_str == "答案":
                    answer_col = col

            # 如果没找到标准列名，尝试模糊匹配
            if question_col is None:
                for col in df.columns:
                    col_str = str(col).strip()
                    if '题目' in col_str or 'question' in col_str.lower():
                        question_col = col
                        break

            if answer_col is None:
                for col in df.columns:
                    col_str = str(col).strip()
                    if '答案' in col_str or 'answer' in col_str.lower():
                        answer_col = col
                        break

            if question_col is None or answer_col is None:
                st.warning(f"工作表'{sheet_name}'中未找到题目列或答案列，跳过")
                continue

            sheet_stats = {
                "total": 0,
                "judgment": 0, "single_choice": 0, "fill_blank": 0, "essay": 0,
                "detection_details": []
            }

            for idx, row in df.iterrows():
                try:
                    question = str(row[question_col]).strip()
                    if pd.isna(question) or question == "" or question == "nan":
                        continue

                    correct_ans = str(row[answer_col]).strip() if not pd.isna(row[answer_col]) else ""

                    # 获取题型列（如果存在）
                    type_col = None
                    for col in df.columns:
                        if str(col).strip() == "题型":
                            type_col = col
                            break

                    explicit_type = row[type_col] if type_col and not pd.isna(row[type_col]) else None

                    # 获取解析列（如果存在）
                    explanation_col = None
                    for col in df.columns:
                        if str(col).strip() == "解析":
                            explanation_col = col
                            break

                    explanation = row[explanation_col] if explanation_col and not pd.isna(row[explanation_col]) else ""

                    # 查找选项列
                    options = []
                    options_text_for_detection = ""

                    # 1. 首先查找名为"选项"的列
                    option_cell_content = None
                    for col in df.columns:
                        if str(col).strip() == "选项":
                            if not pd.isna(row[col]):
                                option_cell_content = row[col]
                            break

                    if option_cell_content is not None:
                        options = parse_options_from_cell(option_cell_content)
                        if options:
                            options_text_for_detection = "\n".join(
                                [f"{opt['label']}. {opt['text']}" for opt in options])
                    else:
                        # 2. 如果没有"选项"列，查找单独的A、B、C、D列
                        options_dict = {}
                        for label in ['A', 'B', 'C', 'D']:
                            possible_columns = [
                                str(label),
                                f"选项{label}",
                                f"{label}选项",
                                f"选项 {label}",
                            ]

                            found = False
                            for col_name in possible_columns:
                                if col_name in df.columns and not pd.isna(row[col_name]) and str(row[col_name]).strip():
                                    options_dict[label] = str(row[col_name]).strip()
                                    found = True
                                    break

                        # 构建选项
                        for label in ['A', 'B', 'C', 'D']:
                            if label in options_dict:
                                options.append({'label': label, 'text': options_dict[label]})

                        if options:
                            options_text_for_detection = "\n".join(
                                [f"{opt['label']}. {opt['text']}" for opt in options])

                    # 智能识别题型
                    detected_type = intelligent_detect_question_type(
                        question, correct_ans, options_text_for_detection, explicit_type
                    )

                    # 标准化答案
                    normalized_ans = normalize_answer(correct_ans)

                    # 统计识别结果
                    sheet_stats["total"] += 1
                    type_key_map = {
                        "判断": "judgment",
                        "单选": "single_choice",
                        "填空": "fill_blank",
                        "简答": "essay"
                    }
                    stat_key = type_key_map.get(detected_type, "unknown")
                    sheet_stats[stat_key] = sheet_stats.get(stat_key, 0) + 1

                    question_data = {
                        "original_index": len(all_questions),
                        "question": question,
                        "type": detected_type,
                        "options": options,
                        "correct_answer_normalized": normalized_ans,
                        "correct_answer_display": correct_ans,
                        "explanation": str(explanation) if pd.notna(explanation) else "",
                        "source": f"{sheet_name}",
                        "row_index": idx + 2,
                        "sheet_name": sheet_name
                    }

                    all_questions.append(question_data)

                except Exception as e:
                    continue

            if sheet_stats["total"] > 0:
                detection_stats[sheet_name] = sheet_stats

        if not all_questions:
            st.error("❌ 未找到任何有效题目")
            return [], {}

        return all_questions, detection_stats

    except Exception as e:
        st.error(f"❌ 加载题库失败: {e}")
        import traceback
        st.error(f"详细错误信息: {traceback.format_exc()}")
        return [], {}


# ================== 主界面 ==================
# 侧边栏
with st.sidebar:
    st.header("🎯 系统导航")

    if st.session_state.get("exam_config"):
        exam_id = st.session_state.exam_config.get("exam_id", "unknown")
        st.info(f"当前题库: {exam_id}")

        # 显示错题统计
        wrong_stats = get_wrong_stats(exam_id)
        if wrong_stats['total'] > 0:
            st.warning(f"⚠️ 错题数: {wrong_stats['total']}")

            if st.button("📖 查看错题本", use_container_width=True):
                wrong_questions = load_wrong_questions(exam_id)
                st.session_state.wrong_questions_list = wrong_questions
                st.session_state.wrong_question_index = 0
                st.session_state.view_wrong_questions = True
                # 重置错题本的会话状态，确保每次进入都不显示答案
                reset_wrong_question_session_state()
                st.rerun()

    st.markdown("---")
    st.subheader("🛠️ 系统工具")

    if st.button("🔄 重新开始", use_container_width=True):
        for key in list(st.session_state.keys()):
            if key not in ["available_exam_files"]:
                del st.session_state[key]
        st.rerun()

    st.markdown("---")
    st.caption("📌 使用说明")
    st.info("""
    1. 选择题库文件
    2. 系统自动识别题型
    3. 选择练习模式
    4. 开始答题
    5. 答错题目自动保存
    6. 下次进入可继续上次进度
    """)

# ================== 错题本界面 ==================
if st.session_state.get("view_wrong_questions", False):
    exam_id = st.session_state.exam_config.get("exam_id", "unknown") if st.session_state.get(
        "exam_config") else "unknown"
    wrong_questions = st.session_state.wrong_questions_list

    if not wrong_questions:
        st.success("🎉 恭喜！您目前没有需要复习的错题！")
        if st.button("返回主界面"):
            st.session_state.view_wrong_questions = False
            st.rerun()
    else:
        idx = st.session_state.wrong_question_index
        if idx < len(wrong_questions):
            wq = wrong_questions[idx]

            st.header(f"📖 错题本（{idx + 1}/{len(wrong_questions)}）")

            # 进度条
            progress = (idx + 1) / len(wrong_questions)
            st.progress(progress, text=f"复习进度: {idx + 1}/{len(wrong_questions)}")

            # 错题信息
            st.markdown("---")
            st.subheader("📝 题目内容")
            st.markdown(f"**题目：** {wq.get('question', '')}")
            st.caption(f"题型：{wq.get('question_type', '')} | 来源：{wq.get('source', '')}")

            st.markdown("---")
            st.markdown("**✍️ 请重新作答：**")

            # 检查是否已提交（使用当前错题的会话状态）
            submitted_key = f"wrong_submitted_{wq.get('question_id', idx)}"
            is_submitted = st.session_state.get(submitted_key, False)

            user_ans = None
            input_key = f"wrong_input_{wq.get('question_id', idx)}"

            if not is_submitted:
                # 根据题型显示不同的输入方式
                if wq.get('question_type') == "单选":
                    options = wq.get('options', [])
                    if options:
                        choices = []
                        for opt in options:
                            if opt.get('label') and opt.get('text'):
                                choices.append(f"{opt['label']}. {opt['text']}")
                            elif opt.get('text'):
                                choices.append(opt['text'])

                        if choices:
                            selected = st.radio("请选择正确答案：", choices, index=None, key=input_key)
                            if selected:
                                # 提取选项字母
                                match = re.match(r'^[\(（\s]*([A-Da-d])[\)）\s]*[\.．、:：]?\s*', selected)
                                if match:
                                    user_ans = match.group(1).upper()
                                else:
                                    user_ans = selected
                        else:
                            user_ans = st.text_input("请输入答案：", value="", key=input_key)
                    else:
                        user_ans = st.text_input("请输入答案：", value="", key=input_key)

                elif wq.get('question_type') == "判断":
                    choice = st.radio("请判断：", ["✅ 对", "❌ 错"], index=None, key=input_key)
                    if choice:
                        user_ans = "对" if choice == "✅ 对" else "错"

                elif wq.get('question_type') == "填空":
                    user_ans = st.text_input("请填写答案：", value="", key=input_key)

                elif wq.get('question_type') == "简答":
                    user_ans = st.text_area("请简要回答：", value="", key=input_key, height=100)

                # 提交按钮
                col1, col2 = st.columns([1, 3])
                with col1:
                    submit_disabled = user_ans is None or str(user_ans).strip() == ""
                    if st.button("✅ 提交答案", type="primary", disabled=submit_disabled, use_container_width=True):
                        # 检查答案
                        is_correct = False
                        user_answer_str = str(user_ans).strip()

                        if wq.get('question_type') == "判断":
                            user_norm = normalize_answer(user_answer_str)
                            correct_norm = wq.get('correct_answer_normalized', '')
                            is_correct = user_norm == correct_norm
                        elif wq.get('question_type') == "单选":
                            user_norm = normalize_answer(user_answer_str)
                            correct_norm = normalize_answer(wq.get('correct_answer', ''))
                            is_correct = user_norm == correct_norm
                        else:  # 填空和简答
                            user_norm = normalize_answer(user_answer_str)
                            correct_norm = normalize_answer(wq.get('correct_answer', ''))
                            is_correct = user_norm == correct_norm

                        # 保存用户答案到会话状态
                        st.session_state[submitted_key] = True
                        st.session_state[f"wrong_user_answer_{wq.get('question_id', idx)}"] = user_ans
                        st.session_state[f"wrong_is_correct_{wq.get('question_id', idx)}"] = is_correct

                        # 更新错题记录到文件
                        # 构建question_data用于更新错题记录
                        question_data = {
                            'question': wq.get('question', ''),
                            'type': wq.get('question_type', ''),
                            'correct_answer_display': wq.get('correct_answer', ''),
                            'correct_answer_normalized': wq.get('correct_answer_normalized', ''),
                            'explanation': wq.get('explanation', ''),
                            'source': wq.get('source', ''),
                            'row_index': int(wq.get('question_id', '0').split('_')[-1]) if '_' in wq.get('question_id',
                                                                                                         '0') else 0
                        }

                        # 更新错题记录
                        filename = get_wrong_questions_filename(exam_id)
                        if os.path.exists(filename):
                            try:
                                with open(filename, 'rb') as f:
                                    all_wrong = pickle.load(f)

                                for wq_item in all_wrong:
                                    if wq_item.get('question_id') == wq.get('question_id'):
                                        wq_item['user_answer'] = user_ans
                                        wq_item['last_attempt'] = datetime.now().isoformat()
                                        wq_item['attempt_count'] = wq_item.get('attempt_count', 0) + 1
                                        wq_item['last_correct'] = is_correct
                                        break

                                with open(filename, 'wb') as f:
                                    pickle.dump(all_wrong, f)
                            except:
                                pass

                        st.rerun()

                with col2:
                    if st.button("🔍 直接查看答案", type="secondary", use_container_width=True):
                        st.session_state[submitted_key] = True
                        st.session_state[f"wrong_user_answer_{wq.get('question_id', idx)}"] = "[未作答]"
                        st.session_state[f"wrong_is_correct_{wq.get('question_id', idx)}"] = False
                        st.rerun()

            else:
                # 显示用户答案和结果
                user_answer = st.session_state.get(f"wrong_user_answer_{wq.get('question_id', idx)}", "")
                is_correct = st.session_state.get(f"wrong_is_correct_{wq.get('question_id', idx)}", False)

                st.markdown("---")
                st.markdown("**📊 你的答案**")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**你的回答：** {user_answer}")
                with col2:
                    if is_correct:
                        st.success("🎉 回答正确！")
                    else:
                        st.error("❌ 回答错误")

                st.markdown("---")
                st.markdown("**✅ 正确答案和解析**")

                # 显示正确答案
                if wq.get('question_type') == "判断":
                    correct_display = "✅ 对" if wq.get('correct_answer_normalized') == "对" else "❌ 错"
                else:
                    correct_display = wq.get('correct_answer', '')

                st.success(f"**正确答案：** {correct_display}")

                # 显示解析
                if wq.get('explanation'):
                    st.info(f"**解析：** {wq['explanation']}")

                # 如果是单选题，显示选项分析
                if wq.get('question_type') == "单选" and wq.get('options'):
                    st.write("**选项分析：**")
                    for opt in wq.get('options', []):
                        label = opt.get('label', '')
                        text = opt.get('text', '')
                        # 检查是否为正确答案
                        correct_answer_norm = normalize_answer(correct_display)
                        if label and correct_answer_norm and label.upper() == correct_answer_norm.upper():
                            st.success(f"✓ {label}. {text} （正确答案）")
                        else:
                            st.write(f"  {label}. {text}")

                # 重新作答按钮
                st.markdown("---")
                if st.button("✏️ 重新作答此题", type="secondary", use_container_width=True):
                    st.session_state[submitted_key] = False
                    st.rerun()

            st.markdown("---")

            # 操作按钮
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if is_submitted and st.session_state.get(f"wrong_is_correct_{wq.get('question_id', idx)}", False):
                    if st.button("✅ 我已掌握", type="primary", use_container_width=True):
                        # 标记为已掌握并从错题本移除
                        if update_wrong_question_status(exam_id, wq.get('question_id'), True):
                            # 从当前列表中移除
                            wrong_questions = [q for q in wrong_questions if
                                               q.get('question_id') != wq.get('question_id')]
                            st.session_state.wrong_questions_list = wrong_questions
                            if st.session_state.wrong_question_index >= len(wrong_questions) and wrong_questions:
                                st.session_state.wrong_question_index = max(0, len(wrong_questions) - 1)
                            elif not wrong_questions:
                                st.session_state.wrong_question_index = 0

                            st.success("已标记为已掌握！")
                            st.rerun()
                else:
                    st.button("✅ 我已掌握", disabled=True, use_container_width=True,
                              help="需回答正确后才能标记为已掌握")

            with col2:
                if st.button("➡️ 下一题", use_container_width=True):
                    st.session_state.wrong_question_index = (idx + 1) % len(wrong_questions)
                    st.rerun()

            with col3:
                if idx > 0 and st.button("⬅️ 上一题", use_container_width=True):
                    st.session_state.wrong_question_index = (idx - 1) % len(wrong_questions)
                    st.rerun()

            with col4:
                if st.button("↩️ 返回主界面", use_container_width=True, type="secondary"):
                    st.session_state.view_wrong_questions = False
                    st.rerun()

        else:
            st.success("🎉 所有错题已复习完成！")
            if st.button("返回主界面"):
                st.session_state.view_wrong_questions = False
                st.rerun()

# ================== 主考试流程 ==================
if not st.session_state.get("view_wrong_questions", False):
    # 步骤1：选择题库
    if not st.session_state.selected_exam_file:
        st.header("📂 第一步：选择题库")

        if not st.session_state.available_exam_files:
            st.error("❌ 未找到任何.xlsx题库文件！")
            st.info("请将题库文件(.xlsx)放在应用目录下的'data'文件夹中，或直接放在应用目录下。")
            st.stop()

        col1, col2 = st.columns([3, 1])
        with col1:
            selected = st.selectbox(
                "**可用题库列表**",
                st.session_state.available_exam_files,
                index=0
            )

        with col2:
            if st.button("✅ 使用此题库", type="primary", use_container_width=True):
                st.session_state.selected_exam_file = selected
                st.session_state.enhanced_loading = True
                st.rerun()

    # 步骤2：加载题库并显示识别结果
    elif st.session_state.selected_exam_file and not st.session_state.exam_started:
        file_path = st.session_state.selected_exam_file
        exam_id = os.path.splitext(file_path)[0]

        st.header("🎯 第二步：题库分析和模式选择")

        if st.session_state.enhanced_loading:
            with st.spinner("🔍 正在智能识别题型..."):
                result = load_questions_with_intelligent_detection(file_path)

                if result[0]:
                    st.session_state.all_questions, st.session_state.detection_stats = result
                    st.session_state.enhanced_loading = False
                    st.success("✅ 题库加载完成！")
                else:
                    st.error("❌ 题库加载失败")
                    st.session_state.enhanced_loading = False

        if st.session_state.all_questions and st.session_state.detection_stats:
            questions = st.session_state.all_questions
            detection_stats = st.session_state.detection_stats

            col1, col2 = st.columns([2, 1])

            with col1:
                st.success(f"✅ **已选择题库：** {file_path}")

                # 显示总体统计
                total_questions = len(questions)
                type_counts = {}
                for q in questions:
                    t = q["type"]
                    type_counts[t] = type_counts.get(t, 0) + 1

                st.write(f"**📊 题库统计**")
                cols = st.columns(4)
                type_names = {"判断": "判断题", "单选": "单选题", "填空": "填空题", "简答": "简答题"}

                for i, (qtype, count) in enumerate(type_counts.items()):
                    with cols[i % 4]:
                        display_name = type_names.get(qtype, qtype)
                        st.metric(label=display_name, value=count)

                # 显示详细识别结果
                st.markdown("---")
                st.subheader("🔍 题型识别详情")

                for sheet_name, stats in detection_stats.items():
                    with st.expander(f"📄 {sheet_name} (共{stats['total']}题)"):
                        st.write("**题型分布：**")
                        type_mapping = {
                            'judgment': '判断题',
                            'single_choice': '单选题',
                            'fill_blank': '填空题',
                            'essay': '简答题'
                        }
                        for t_key, t_name in type_mapping.items():
                            count = stats.get(t_key, 0)
                            if count > 0:
                                st.write(f"- {t_name}: {count}题")

                # 练习设置
                st.markdown("---")
                st.subheader("🎯 练习设置")

                mode = st.radio(
                    "**请选择练习模式**:",
                    ["顺序练习", "自主选题", "题型专项"],
                    index=0
                )

                if mode == "顺序练习":
                    available_types = list(type_counts.keys())
                    selected_types = st.multiselect(
                        "**请选择题型**（可多选）:",
                        options=available_types,
                        default=available_types,
                        format_func=lambda x: f"{type_names.get(x, x)} ({type_counts[x]}道)"
                    )

                    if selected_types:
                        total_selected = sum(type_counts.get(t, 0) for t in selected_types)
                        st.info(f"已选择 {len(selected_types)} 种题型，共 {total_selected} 题")

                        max_questions = st.slider(
                            "**题目数量限制**:",
                            min_value=1,
                            max_value=total_selected,
                            value=min(20, total_selected)
                        )

                        if st.button("🚀 开始顺序练习", type="primary", use_container_width=True):
                            # 筛选题目
                            filtered = []
                            for q in questions:
                                if q["type"] in selected_types:
                                    filtered.append({**q, "filtered_index": len(filtered)})

                            if len(filtered) > max_questions:
                                random.seed(42)
                                filtered = random.sample(filtered, max_questions)
                                filtered.sort(key=lambda x: x["original_index"])

                            st.session_state.filtered_questions = filtered
                            st.session_state.current_index = 0
                            st.session_state.selected_types = selected_types
                            st.session_state.exam_config = {
                                "exam_id": exam_id,
                                "selected_types": selected_types,
                                "total": len(filtered),
                                "mode": "顺序练习"
                            }
                            st.session_state.exam_started = True

                            # 保存初始进度
                            save_progress(exam_id, {}, st.session_state.exam_config, {
                                "current_index": 0,
                                "filtered_questions_length": len(filtered)
                            })
                            st.rerun()

                elif mode == "自主选题":
                    st.info("在此模式下，您可以自由选择要练习的题目")

                    if st.button("🚀 进入自主选题界面", type="primary", use_container_width=True):
                        st.session_state.question_selection_mode = True
                        st.session_state.exam_config = {
                            "exam_id": exam_id,
                            "mode": "自主选题"
                        }
                        st.session_state.exam_started = True
                        st.rerun()

                elif mode == "题型专项":
                    selected_type = st.selectbox(
                        "**请选择专项练习的题型**:",
                        options=list(type_counts.keys()),
                        format_func=lambda x: f"{type_names.get(x, x)} ({type_counts[x]}道)"
                    )

                    if selected_type:
                        type_count = type_counts[selected_type]
                        max_questions = st.slider(
                            "**练习题目数量**:",
                            min_value=1,
                            max_value=type_count,
                            value=min(20, type_count)
                        )

                        if st.button("🚀 开始专项练习", type="primary", use_container_width=True):
                            filtered = []
                            for q in questions:
                                if q["type"] == selected_type:
                                    filtered.append({**q, "filtered_index": len(filtered)})

                            if len(filtered) > max_questions:
                                random.seed(42)
                                filtered = random.sample(filtered, max_questions)
                                filtered.sort(key=lambda x: x["original_index"])

                            st.session_state.filtered_questions = filtered
                            st.session_state.current_index = 0
                            st.session_state.selected_types = [selected_type]
                            st.session_state.exam_config = {
                                "exam_id": exam_id,
                                "selected_types": [selected_type],
                                "total": len(filtered),
                                "mode": "题型专项"
                            }
                            st.session_state.exam_started = True

                            # 保存初始进度
                            save_progress(exam_id, {}, st.session_state.exam_config, {
                                "current_index": 0,
                                "filtered_questions_length": len(filtered)
                            })
                            st.rerun()

            with col2:
                st.markdown("**📁 进度管理**")

                saved_progress, saved_config, saved_extra = load_progress(exam_id)

                if saved_progress:
                    completed = len([v for v in saved_progress.values() if v.get("answer")])
                    correct = len([v for v in saved_progress.values() if v.get("correct", False)])
                    current_index = saved_extra.get("current_index", 0)

                    st.success("📊 发现历史进度：")
                    st.write(f"已答题: {completed}/{saved_extra.get('filtered_questions_length', '未知')}")
                    st.write(f"正确数: {correct}")
                    st.write(f"当前进度: {current_index + 1}/{saved_extra.get('filtered_questions_length', '未知')}")

                    col_a, col_b = st.columns(2)

                    with col_a:
                        if st.button("🔄 继续上次练习", use_container_width=True, type="primary"):
                            # 恢复所有状态
                            st.session_state.all_questions = questions
                            st.session_state.exam_config = saved_config
                            st.session_state.user_progress = saved_progress
                            st.session_state.exam_started = True

                            mode = saved_config.get("mode", "顺序练习")
                            if mode in ["顺序练习", "题型专项"]:
                                selected_types = saved_config.get("selected_types", [])
                                filtered = []
                                for q in questions:
                                    if q["type"] in selected_types:
                                        filtered.append({**q, "filtered_index": len(filtered)})

                                saved_length = saved_extra.get("filtered_questions_length", 0)
                                if saved_length > 0 and len(filtered) != saved_length:
                                    st.warning("题目数量与保存的进度不一致，可能题库已更新")

                                st.session_state.filtered_questions = filtered
                                st.session_state.current_index = current_index
                                st.session_state.selected_types = selected_types

                                # 恢复已提交状态
                                for i in range(len(filtered)):
                                    if i in saved_progress and saved_progress[i].get("answer"):
                                        st.session_state.answer_submitted[f"submitted_{exam_id}_{i}"] = True

                                st.success(f"已恢复进度，从第 {current_index + 1} 题开始")
                            elif mode == "自主选题":
                                st.session_state.question_selection_mode = True

                            st.rerun()

                    with col_b:
                        if st.button("🗑️ 清除进度", use_container_width=True, type="secondary"):
                            if clear_progress(exam_id):
                                st.success("进度已清除！")
                                st.rerun()
                else:
                    st.info("暂无历史进度")

                st.markdown("---")
                st.caption("💡 识别算法说明")
                st.info("""
                **智能识别功能**：
                - ✅ 支持多种选项格式
                - ✅ 智能判断题型特征
                - ✅ 详细的题型统计
                - ✅ 自动保存进度
                """)

                if st.button("↩️ 更换题库", use_container_width=True, type="secondary"):
                    st.session_state.selected_exam_file = None
                    st.rerun()

    # 步骤3：自主选题模式
    elif (st.session_state.exam_started and
          st.session_state.question_selection_mode):

        questions = st.session_state.all_questions
        exam_id = st.session_state.exam_config["exam_id"]

        st.header("🎯 自主选题模式")
        st.info("请选择您要练习的题目（可多选）")

        # 搜索功能
        search_term = st.text_input("🔍 搜索题目关键词", "")

        selected_indices = st.session_state.selected_question_indices.copy()

        # 答题状态统计
        answered = 0
        correct = 0
        wrong = 0
        not_answered = 0

        for idx, q in enumerate(questions):
            record = st.session_state.user_progress.get(idx, {})
            if record.get("answer"):
                answered += 1
                if record.get("correct", False):
                    correct += 1
                else:
                    wrong += 1
            else:
                not_answered += 1

        # 显示统计信息
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总题数", len(questions))
        with col2:
            st.metric("已答题", answered)
        with col3:
            st.metric("答对数", correct)
        with col4:
            st.metric("答错数", wrong)

        # 状态筛选
        status_options = ["全部", "未作答", "已答对", "已答错"]
        selected_status = st.selectbox("📊 筛选答题状态", options=status_options, index=0)

        st.markdown("---")

        # 显示题目列表
        for idx, q in enumerate(questions):
            if search_term and search_term.lower() not in q["question"].lower():
                continue

            # 获取答题状态
            record = st.session_state.user_progress.get(idx, {})
            has_answer = bool(record.get("answer"))
            is_correct = record.get("correct", False)

            # 状态筛选
            if selected_status == "未作答" and has_answer:
                continue
            elif selected_status == "已答对" and (not has_answer or not is_correct):
                continue
            elif selected_status == "已答错" and (not has_answer or is_correct):
                continue

            # 确定状态标记和颜色
            if not has_answer:
                status_icon = "⚪"
                status_text = "未作答"
                status_color = "gray"
            elif is_correct:
                status_icon = "✅"
                status_text = "已答对"
                status_color = "green"
            else:
                status_icon = "❌"
                status_text = "已答错"
                status_color = "red"

            col1, col2, col3, col4 = st.columns([1, 1, 6, 1])
            with col1:
                status = "✅" if idx in selected_indices else "⬜"
                st.write(f"**{idx + 1}.** {status}")
            with col2:
                st.markdown(f"<span style='color:{status_color}'>{status_icon}</span>", unsafe_allow_html=True)
                st.caption(status_text)
            with col3:
                if has_answer:
                    user_answer = record.get("answer", "")
                    st.write(f"**题目：** {q['question'][:80]}...")
                    st.caption(
                        f"你的答案：{user_answer[:30]}..." if len(user_answer) > 30 else f"你的答案：{user_answer}")
                else:
                    st.write(f"**题目：** {q['question'][:80]}...")
                st.caption(f"题型: {q['type']} | 来源: {q['source']}")
            with col4:
                if idx in selected_indices:
                    if st.button("❌", key=f"remove_{idx}", help="取消选择"):
                        selected_indices.remove(idx)
                        st.rerun()
                else:
                    if st.button("➕", key=f"add_{idx}", help="选择此题"):
                        selected_indices.append(idx)
                        st.rerun()

        # 更新选择的题目
        st.session_state.selected_question_indices = selected_indices

        st.markdown("---")

        # 选择统计和操作
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("已选题数", len(selected_indices))

        with col2:
            if st.button("📝 全选所有题目", use_container_width=True):
                st.session_state.selected_question_indices = list(range(len(questions)))
                st.rerun()

            if st.button("🗑️ 清空选择", use_container_width=True):
                st.session_state.selected_question_indices = []
                st.rerun()

        with col3:
            if len(selected_indices) > 0:
                if st.button("🚀 开始练习选定题目", type="primary", use_container_width=True):
                    filtered = []
                    for original_idx in selected_indices:
                        if original_idx < len(questions):
                            q = questions[original_idx]
                            filtered.append({**q, "filtered_index": len(filtered)})

                    st.session_state.filtered_questions = filtered
                    st.session_state.current_index = 0
                    st.session_state.question_selection_mode = False
                    st.session_state.exam_config["total"] = len(filtered)

                    # 保存初始进度
                    save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                        "current_index": 0,
                        "filtered_questions_length": len(filtered)
                    })
                    st.rerun()
            else:
                st.button("🚀 开始练习选定题目", disabled=True, use_container_width=True)

    # 步骤4：答题界面
    elif (st.session_state.exam_started and
          "selected_types" in st.session_state and
          st.session_state.current_index < len(st.session_state.filtered_questions)):

        questions = st.session_state.filtered_questions
        idx = st.session_state.current_index
        q = questions[idx]
        exam_id = st.session_state.exam_config["exam_id"]

        # 顶部进度
        progress = (idx + 1) / len(questions)
        st.progress(progress, text=f"进度: {idx + 1}/{len(questions)}")

        # 题目显示
        st.header(f"第 {idx + 1} 题 / 共 {len(questions)} 题")
        st.subheader(q['question'])
        st.caption(f"题型：{q['type']} | 来源：{q['source']}")

        # 检查是否已提交
        submitted_key = f"submitted_{exam_id}_{idx}"
        is_submitted = st.session_state.answer_submitted.get(submitted_key, False)

        previous_record = st.session_state.user_progress.get(q["original_index"], {})
        previous_answer = previous_record.get("answer", "")
        previous_correct = previous_record.get("correct", None)

        input_key = f"input_{exam_id}_{q['original_index']}_{idx}"

        # 答题区域
        st.markdown("---")
        st.markdown("**✍️ 请作答：**")

        user_ans = None

        if not is_submitted:
            if q["type"] == "单选":
                if q["options"]:
                    choices = []
                    for opt in q["options"]:
                        if opt['label'] and opt['text']:
                            choices.append(f"{opt['label']}. {opt['text']}")
                        elif opt['text']:
                            choices.append(opt["text"])

                    if choices:
                        selected = st.radio("请选择正确答案：", choices, index=None, key=input_key)
                        user_ans = selected
                    else:
                        user_ans = st.text_input("请输入答案：", value=previous_answer or "", key=input_key)
                else:
                    user_ans = st.text_input("请输入答案：", value=previous_answer or "", key=input_key)

            elif q["type"] == "判断":
                choice = st.radio("请判断：", ["✅ 对", "❌ 错"], index=None, key=input_key)
                if choice:
                    user_ans = "对" if choice == "✅ 对" else "错"

            elif q["type"] == "填空":
                user_ans = st.text_input("请填写答案：", value=previous_answer or "", key=input_key)

            elif q["type"] == "简答":
                user_ans = st.text_area("请简要回答：", value=previous_answer or "", key=input_key, height=100)
        else:
            # 显示已提交的答案
            if previous_answer:
                st.info(f"**你的答案：** {previous_answer}")

            st.markdown("---")
            st.markdown("**📊 正确答案和解析**")

            if q["type"] == "判断":
                correct_display = "✅ 对" if q["correct_answer_normalized"] == "对" else "❌ 错"
            else:
                correct_display = q["correct_answer_display"]

            col1, col2 = st.columns(2)
            with col1:
                st.success(f"**正确答案：** {correct_display}")
            with col2:
                if previous_correct is not None:
                    if previous_correct:
                        st.success("🎉 回答正确！")
                    else:
                        st.error("❌ 回答错误")

            if q.get("explanation"):
                st.info(f"**解析：** {q['explanation']}")

            if q["type"] == "单选" and q["options"]:
                st.write("**选项分析：**")
                for opt in q["options"]:
                    label = opt.get('label', '')
                    text = opt.get('text', '')
                    # 检查是否为正确答案
                    correct_answer_norm = normalize_answer(correct_display)
                    if label and correct_answer_norm and label.upper() == correct_answer_norm.upper():
                        st.success(f"✓ {label}. {text} （正确答案）")
                    else:
                        st.write(f"  {label}. {text}")

        st.markdown("---")

        # 操作按钮
        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1:
            if not is_submitted:
                submit_disabled = user_ans is None or str(user_ans).strip() == ""
                if st.button("✅ 提交答案", type="primary", disabled=submit_disabled, use_container_width=True):
                    is_correct = check_answer(user_ans, q)
                    record = {
                        "answer": user_ans,
                        "correct": is_correct,
                        "time": datetime.now().isoformat(),
                        "question": q["question"],
                        "correct_answer": q["correct_answer_display"],
                        "explanation": q.get("explanation", "")
                    }
                    st.session_state.user_progress[q["original_index"]] = record
                    st.session_state.answer_submitted[submitted_key] = True

                    # 保存进度（包括当前索引）
                    save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                        "current_index": idx,
                        "filtered_questions_length": len(questions)
                    })

                    if not is_correct and user_ans:
                        save_wrong_question(exam_id, q, user_ans, is_correct)
                        st.warning("❌ 答错了！此题目已保存到错题本")
                    st.rerun()
            else:
                if st.button("➡️ 下一题", type="primary", use_container_width=True):
                    st.session_state.current_index += 1

                    # 保存进度（包括新的当前索引）
                    save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                        "current_index": st.session_state.current_index,
                        "filtered_questions_length": len(questions)
                    })
                    st.rerun()

        with col2:
            if st.button("⏭ 跳过", use_container_width=True):
                st.session_state.current_index += 1

                # 保存进度
                save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                    "current_index": st.session_state.current_index,
                    "filtered_questions_length": len(questions)
                })
                st.rerun()

        with col3:
            if idx > 0 and st.button("⬅️ 上一题", use_container_width=True):
                st.session_state.current_index -= 1

                # 保存进度
                save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                    "current_index": st.session_state.current_index,
                    "filtered_questions_length": len(questions)
                })
                st.rerun()

        with col4:
            if not is_submitted:
                if st.button("🔍 查看答案", use_container_width=True, type="secondary"):
                    st.session_state.answer_submitted[submitted_key] = True

                    # 保存进度
                    save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                        "current_index": idx,
                        "filtered_questions_length": len(questions)
                    })
                    st.rerun()
            else:
                if st.button("✏️ 重新作答", use_container_width=True, type="secondary"):
                    st.session_state.answer_submitted[submitted_key] = False

                    # 保存进度
                    save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                        "current_index": idx,
                        "filtered_questions_length": len(questions)
                    })
                    st.rerun()

        with col5:
            if st.button("📥 保存进度", use_container_width=True, type="secondary"):
                if user_ans and not is_submitted:
                    record = {
                        "answer": user_ans,
                        "correct": False,
                        "time": datetime.now().isoformat(),
                        "question": q["question"]
                    }
                    st.session_state.user_progress[q["original_index"]] = record

                # 保存进度
                save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config, {
                    "current_index": idx,
                    "filtered_questions_length": len(questions)
                })
                st.success("进度已保存！")

        with col6:
            if st.button("📋 题目列表", use_container_width=True, type="secondary"):
                st.session_state.show_question_list = True
                st.rerun()

        # 题目导航
        if st.session_state.get("show_question_list", False):
            st.markdown("---")
            st.subheader("📋 题目导航")

            cols_per_row = 10
            total_questions = len(questions)

            for row in range(0, total_questions, cols_per_row):
                cols = st.columns(cols_per_row)
                end_idx = min(row + cols_per_row, total_questions)

                for i in range(row, end_idx):
                    col_idx = i - row
                    q_progress = st.session_state.user_progress.get(questions[i]["original_index"], {})

                    if q_progress.get("answer"):
                        if q_progress.get("correct", False):
                            question_status = "✅"
                        else:
                            question_status = "❌"
                    else:
                        question_status = "○"

                    current_indicator = "➤" if i == idx else ""

                    with cols[col_idx]:
                        if st.button(f"{question_status}{current_indicator}{i + 1}",
                                     key=f"nav_{i}",
                                     use_container_width=True,
                                     type="secondary" if i == idx else "secondary"):
                            st.session_state.current_index = i
                            st.session_state.show_question_list = False
                            st.rerun()

        # 统计信息
        st.markdown("---")
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        with col_stat1:
            answered = len([v for v in st.session_state.user_progress.values() if v.get("answer")])
            st.metric("已答题", f"{answered}/{len(questions)}")
        with col_stat2:
            correct = len([v for v in st.session_state.user_progress.values() if v.get("correct", False)])
            st.metric("正确数", correct)
        with col_stat3:
            wrong_stats = get_wrong_stats(exam_id)
            st.metric("错题数", wrong_stats['total'])
        with col_stat4:
            if answered > 0:
                accuracy = (correct / answered) * 100
                st.metric("正确率", f"{accuracy:.1f}%")
            else:
                st.metric("正确率", "0%")

    # 步骤5：练习完成
    elif (st.session_state.exam_started and
          "selected_types" in st.session_state and
          st.session_state.current_index >= len(st.session_state.filtered_questions)):

        st.balloons()
        st.success("🎉 练习完成！")

        questions = st.session_state.filtered_questions
        exam_id = st.session_state.exam_config["exam_id"]

        # 计算统计
        total = len(questions)
        answered = len([v for v in st.session_state.user_progress.values() if v.get("answer")])
        correct = len([v for v in st.session_state.user_progress.values() if v.get("correct", False)])
        accuracy = correct / answered * 100 if answered > 0 else 0

        # 错题统计
        wrong_stats = get_wrong_stats(exam_id)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总题数", total)
        with col2:
            st.metric("正确数", correct)
        with col3:
            st.metric("错题数", wrong_stats['total'])
        with col4:
            st.metric("正确率", f"{accuracy:.1f}%")

        if wrong_stats['total'] > 0:
            st.warning(f"⚠️ 本次练习有 {wrong_stats['total']} 道错题需要复习！")

        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if st.button("🔄 重新练习", use_container_width=True, type="primary"):
                st.session_state.current_index = 0
                st.session_state.user_progress = {}
                st.session_state.answer_submitted = {}

                # 保存重置后的进度
                save_progress(exam_id, {}, st.session_state.exam_config, {
                    "current_index": 0,
                    "filtered_questions_length": len(questions)
                })
                st.rerun()

        with col_b:
            if st.button("📋 自主选题", use_container_width=True):
                st.session_state.question_selection_mode = True
                st.session_state.current_index = 0
                st.rerun()

        with col_c:
            if st.button("🏠 返回首页", use_container_width=True, type="secondary"):
                for key in ["exam_started", "selected_types", "current_index", "user_progress",
                            "filtered_questions", "all_questions", "exam_config", "answer_submitted"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()