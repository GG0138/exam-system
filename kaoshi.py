import sys

print("已安装的包：", [pkg for pkg in sys.modules if 'openpy' in pkg])
import streamlit as st
import pandas as pd
import re
import os
import json
import pickle
import hashlib
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="智能考试系统", page_icon="📚", layout="wide")
st.title("📚 智能考试系统（带答案提示和错题本）")


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
                    'attempt_count': wq.get('attempt_count', 0) + 1
                })
                exists = True
                break

        if not exists and not is_correct:  # 只保存错误的题目
            wrong_question = {
                'question_id': question_id,
                'question': question_data.get('question', ''),
                'question_type': question_data.get('type', ''),
                'correct_answer': question_data.get('correct_answer_display', ''),
                'user_answer': user_answer,
                'explanation': question_data.get('explanation', ''),
                'source': question_data.get('source', ''),
                'first_wrong': datetime.now().isoformat(),
                'last_attempt': datetime.now().isoformat(),
                'attempt_count': 1,
                'reviewed': False
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


# ================== 工具函数：进度保存/加载 ==================
def get_progress_filename(exam_id):
    """生成进度文件名"""
    progress_dir = "progress_data"
    if not os.path.exists(progress_dir):
        os.makedirs(progress_dir)
    exam_hash = hashlib.md5(exam_id.encode()).hexdigest()[:8]
    return os.path.join(progress_dir, f"progress_{exam_hash}.pkl")


def save_progress(exam_id, progress_data, config_data=None):
    """保存进度到文件"""
    try:
        filename = get_progress_filename(exam_id)
        data = {
            "progress": progress_data,
            "config": config_data or {},
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
                if (datetime.now() - file_time).days > 7:
                    return {}, {}
            return data.get("progress", {}), data.get("config", {})
    except Exception as e:
        st.error(f"加载进度失败: {e}")
    return {}, {}


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
    if not answer:
        return ""
    answer = str(answer).strip()
    if answer in ["✅", "对", "正确", "√", "true", "True", "T", "t"]:
        return "对"
    elif answer in ["❌", "错", "错误", "×", "false", "False", "F", "f"]:
        return "错"
    return answer


def check_answer(user_input, question):
    """判分函数"""
    if not user_input or str(user_input).strip() == "":
        return False
    user_input = str(user_input).strip()
    correct_disp = str(question["correct_answer_display"]).strip()
    correct_norm = str(question["correct_answer_normalized"]).strip()
    q_type = question["type"]
    user_norm = normalize_answer(user_input)

    if q_type == "单选":
        user_match = re.match(r'^[\(（]?([A-Da-d1-4])[\)）]?[\.．:\s]*', user_input)
        correct_match = re.match(r'^[\(（]?([A-Da-d1-4])[\)）]?[\.．:\s]*', correct_disp)
        if user_match and correct_match:
            return user_match.group(1).upper() == correct_match.group(1).upper()
        else:
            return user_norm == normalize_answer(correct_disp)
    elif q_type == "判断":
        return user_norm == correct_norm
    elif q_type == "填空":
        return user_norm == normalize_answer(correct_disp)
    elif q_type == "简答":
        import unicodedata
        def normalize_text(text):
            text = unicodedata.normalize('NFKC', text)
            text = re.sub(r'[\s\p{P}\p{S}]+', '', text, flags=re.UNICODE)
            return text.lower()

        user_clean = normalize_text(user_input)
        correct_clean = normalize_text(correct_disp)
        similarity = 0
        if len(correct_clean) > 0:
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, user_clean, correct_clean).ratio()
        return similarity >= 0.9
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

if "selected_exam_file" not in st.session_state:
    st.session_state.selected_exam_file = None

if "all_questions" not in st.session_state:
    st.session_state.all_questions = []

if "filtered_questions" not in st.session_state:
    st.session_state.filtered_questions = []

if "current_index" not in st.session_state:
    st.session_state.current_index = 0

if "user_progress" not in st.session_state:
    st.session_state.user_progress = {}

if "exam_config" not in st.session_state:
    st.session_state.exam_config = {}

if "exam_started" not in st.session_state:
    st.session_state.exam_started = False

if "show_answer" not in st.session_state:
    st.session_state.show_answer = {}


# ================== 加载指定题库 ==================
@st.cache_resource
def load_questions_from_file(file_path):
    """从Excel文件加载题库"""
    try:
        if not os.path.exists(file_path):
            data_path = os.path.join("data", file_path)
            if os.path.exists(data_path):
                file_path = data_path
            else:
                st.error(f"❌ 找不到题库文件: {file_path}")
                return []

        sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')
        if not sheets:
            st.error("❌ Excel文件为空或格式不正确")
            return []

        all_questions = []
        for sheet_name, df in sheets.items():
            if "题目" not in df.columns or "正确答案" not in df.columns:
                continue

            for idx, row in df.iterrows():
                try:
                    question = str(row["题目"]).strip()
                    if not question:
                        continue

                    correct_ans = str(row["正确答案"]).strip()
                    option_col = row.get("选项", "")
                    explicit_type = row.get("题型", None)
                    explanation = row.get("解析", "")

                    options = []
                    if pd.notna(option_col) and str(option_col).strip():
                        lines = str(option_col).strip().splitlines()
                        for line in lines:
                            line = line.strip()
                            if not line: continue
                            match = re.match(r'^[\(（]?([A-Da-d1-4])[\)）]?[\.．:\s]', line)
                            if match:
                                label = match.group(1).upper()
                                text = line[match.end():].strip()
                                options.append({"label": label, "text": text})
                            else:
                                options.append({"label": "", "text": line})

                    is_judgment = lambda x: normalize_answer(x) in ["对", "错"]
                    if explicit_type and str(explicit_type).strip() in ["判断", "单选", "填空", "简答"]:
                        q_type = str(explicit_type).strip()
                    elif is_judgment(correct_ans):
                        q_type = "判断"
                    elif options:
                        q_type = "单选"
                    else:
                        q_type = "填空"

                    normalized_ans = normalize_answer(correct_ans)

                    all_questions.append({
                        "original_index": len(all_questions),
                        "question": question,
                        "type": q_type,
                        "options": options,
                        "correct_answer_normalized": normalized_ans,
                        "correct_answer_display": correct_ans,
                        "explanation": str(explanation) if pd.notna(explanation) else "",
                        "source": f"{sheet_name}",
                        "row_index": idx + 2
                    })

                except Exception as e:
                    continue

        return all_questions

    except Exception as e:
        st.error(f"❌ 加载题库失败: {e}")
        return []


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
                with st.expander("📋 错题列表", expanded=True):
                    for i, wq in enumerate(wrong_questions):
                        st.write(f"**{i + 1}. {wq.get('question', '')[:60]}...**")
                        st.caption(f"你的答案: {wq.get('user_answer', '')} | 正确答案: {wq.get('correct_answer', '')}")
                        if st.button(f"删除第{i + 1}题", key=f"del_{i}"):
                            # 简单的删除功能
                            pass

    st.markdown("---")
    st.subheader("🛠️ 系统工具")

    if st.button("🔄 重新开始", use_container_width=True):
        for key in ["exam_started", "selected_types", "current_index", "user_progress",
                    "filtered_questions", "all_questions", "exam_config",
                    "selected_exam_file", "show_answer"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    st.markdown("---")
    st.caption("📌 使用说明")
    st.info("""
    1. 选择题库文件
    2. 选择练习题型
    3. 开始答题
    4. 答错题目自动保存
    5. 可使用提示功能
    """)

# 步骤1：选择题库
if not st.session_state.selected_exam_file:
    st.header("📂 第一步：选择题库")

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
            st.rerun()

# 步骤2：加载题库
elif st.session_state.selected_exam_file and not st.session_state.exam_started:
    file_path = st.session_state.selected_exam_file
    exam_id = os.path.splitext(file_path)[0]

    st.header("🎯 第二步：配置练习")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.success(f"✅ **已选择题库：** {file_path}")

        with st.spinner("正在加载题库..."):
            questions = load_questions_from_file(file_path)

        if questions:
            st.session_state.all_questions = questions

            # 统计题型
            type_counts = {}
            for q in questions:
                t = q["type"]
                type_counts[t] = type_counts.get(t, 0) + 1

            st.write(f"**📊 题库统计**")
            cols = st.columns(min(4, len(type_counts)))
            for i, (qtype, count) in enumerate(type_counts.items()):
                with cols[i % len(cols)]:
                    st.metric(label=f"{qtype}题", value=count)

            st.markdown("---")
            st.subheader("🎯 选择练习题型")

            # 题型选择
            selected_types = st.multiselect(
                "**请选择题型**（可多选）:",
                options=list(type_counts.keys()),
                default=list(type_counts.keys()),
                format_func=lambda x: f"{x}题 ({type_counts[x]}道)"
            )

            if selected_types:
                total_selected = sum(type_counts.get(t, 0) for t in selected_types)
                st.info(f"已选择 {len(selected_types)} 种题型，共 {total_selected} 题")

                # 题目数量限制
                max_questions = st.slider(
                    "**题目数量限制**:",
                    min_value=1,
                    max_value=total_selected,
                    value=min(20, total_selected)
                )

                if st.button("🚀 开始练习", type="primary", use_container_width=True):
                    # 筛选题目
                    filtered = []
                    for q in questions:
                        if q["type"] in selected_types:
                            filtered.append({**q, "filtered_index": len(filtered)})

                    # 限制题目数量
                    if len(filtered) > max_questions:
                        import random

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
                        "max_questions": max_questions
                    }
                    st.session_state.exam_started = True
                    save_progress(exam_id, {}, st.session_state.exam_config)
                    st.rerun()

    with col2:
        st.markdown("**📁 进度管理**")

        # 尝试加载历史进度
        saved_progress, saved_config = load_progress(exam_id)

        if saved_progress:
            completed = len([v for v in saved_progress.values() if v.get("answer")])
            correct = len([v for v in saved_progress.values() if v.get("correct", False)])

            st.success(f"发现历史进度：")
            st.write(f"已答题: {completed}")
            st.write(f"正确数: {correct}")

            if st.button("🔄 继续上次练习", use_container_width=True, type="primary"):
                st.session_state.all_questions = questions
                st.session_state.exam_config = {"exam_id": exam_id}
                st.session_state.user_progress = saved_progress
                st.session_state.exam_started = True
                st.rerun()

        if st.button("↩️ 更换题库", use_container_width=True, type="secondary"):
            st.session_state.selected_exam_file = None
            st.rerun()

# 步骤3：答题界面（带提示答案功能）
elif (st.session_state.exam_started and
      "selected_types" in st.session_state and
      st.session_state.current_index < len(st.session_state.filtered_questions)):

    questions = st.session_state.filtered_questions
    idx = st.session_state.current_index
    q = questions[idx]
    exam_id = st.session_state.exam_config["exam_id"]

    # 顶部进度条
    progress = (idx + 1) / len(questions)
    st.progress(progress, text=f"进度: {idx + 1}/{len(questions)}")

    # 题目显示
    st.header(f"第 {idx + 1} 题 / 共 {len(questions)} 题")
    st.subheader(q['question'])
    st.caption(f"题型：{q['type']} | 来源：{q['source']}")

    # ================== 新增：提示答案区域 ==================
    with st.expander("💡 需要帮助？点击查看提示和答案", expanded=False):
        tab1, tab2, tab3 = st.tabs(["答题技巧", "查看答案", "题目解析"])

        with tab1:
            if q["type"] == "判断":
                st.info("**判断题技巧：**")
                st.write("• 关注绝对化词语（如'总是'、'绝不'）")
                st.write("• 注意概念的正确定义")
                st.write("• 区分相似但不同的概念")
            elif q["type"] == "单选":
                st.info("**单选题技巧：**")
                st.write("• 先排除明显错误的选项")
                st.write("• 关注选项中的关键词")
                st.write("• 比较相似选项的细微差别")
            elif q["type"] == "填空":
                st.info("**填空题技巧：**")
                st.write("• 注意术语的准确性")
                st.write("• 关注上下文的关键词")
                st.write("• 检查拼写和格式")
            elif q["type"] == "简答":
                st.info("**简答题技巧：**")
                st.write("• 抓住核心概念")
                st.write("• 分点作答更清晰")
                st.write("• 使用专业术语")

        with tab2:
            st.success("**正确答案：**")
            if q["type"] == "判断":
                correct_display = "✅ 对" if q["correct_answer_normalized"] == "对" else "❌ 错"
            else:
                correct_display = q["correct_answer_display"]
            st.write(correct_display)

            # 如果是选择题，显示选项分析
            if q["type"] == "单选" and q["options"]:
                st.write("**选项分析：**")
                for opt in q["options"]:
                    label = opt.get('label', '')
                    text = opt.get('text', '')
                    if label and correct_display.startswith(label):
                        st.success(f"✓ {label}. {text} （正确答案）")
                    else:
                        st.write(f"  {label}. {text}")

        with tab3:
            if q.get("explanation"):
                st.info("**题目解析：**")
                st.write(q["explanation"])
            else:
                st.info("本题暂无详细解析")

    # 答题区域
    st.markdown("---")
    st.markdown("**✍️ 请作答：**")

    previous_answer = st.session_state.user_progress.get(q["original_index"], {}).get("answer", "")
    input_key = f"input_{exam_id}_{q['original_index']}_{idx}"

    user_ans = None

    if q["type"] == "单选":
        if q["options"]:
            choices = []
            for opt in q["options"]:
                if opt['label']:
                    choices.append(f"{opt['label']}. {opt['text']}")
                else:
                    choices.append(opt["text"])

            selected = st.radio("请选择正确答案：", choices, index=None, key=input_key)
            user_ans = selected
        else:
            user_ans = st.text_input("请输入答案：", value=previous_answer or "", key=input_key)

    elif q["type"] == "判断":
        choice = st.radio("请判断：", ["✅ 对", "❌ 错"], index=None, key=input_key, horizontal=True)
        user_ans = "对" if choice == "✅ 对" else "错" if choice == "❌ 错" else None

    elif q["type"] == "填空":
        user_ans = st.text_input("请输入答案：", value=previous_answer or "", key=input_key)

    elif q["type"] == "简答":
        user_ans = st.text_area("请输入答案：", value=previous_answer or "", height=100, key=input_key)

    st.markdown("---")

    # ================== 操作按钮（增加提示答案按钮） ==================
    col1, col2, col3, col4, col5 = st.columns(5)  # 改为5列

    with col1:
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
            save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config)

            # 保存到错题本（如果答错）
            if not is_correct and user_ans:
                save_wrong_question(exam_id, q, user_ans, is_correct)
                st.warning("❌ 答错了！此题目已保存到错题本")
            st.rerun()

    with col2:
        if st.button("⏭ 跳过", use_container_width=True):
            st.session_state.current_index += 1
            st.rerun()

    with col3:
        if idx > 0 and st.button("⬅️ 上一题", use_container_width=True):
            st.session_state.current_index -= 1
            st.rerun()

    # ===== 新增：快速查看答案按钮 =====
    with col4:
        show_answer_key = f"show_answer_{exam_id}_{idx}"
        if st.button("🔍 快速查看答案", use_container_width=True, type="secondary"):
            st.session_state[show_answer_key] = True
            st.rerun()

        # 显示答案（如果用户点击了快速查看）
        if st.session_state.get(show_answer_key, False):
            if q["type"] == "判断":
                answer_display = "✅ 对" if q["correct_answer_normalized"] == "对" else "❌ 错"
            else:
                answer_display = q["correct_answer_display"]
            st.info(f"**答案：** {answer_display}")

    with col5:
        if st.button("📥 保存进度", use_container_width=True, type="secondary"):
            if user_ans:
                record = {
                    "answer": user_ans,
                    "correct": False,
                    "time": datetime.now().isoformat(),
                    "question": q["question"]
                }
                st.session_state.user_progress[q["original_index"]] = record
            save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config)
            st.success("进度已保存！")

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

# 步骤4：练习完成
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

    # 错题提示
    if wrong_stats['total'] > 0:
        st.warning(f"⚠️ 本次练习有 {wrong_stats['total']} 道错题需要复习！")

    # 操作按钮
    st.markdown("---")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🔄 重新练习", use_container_width=True, type="primary"):
            st.session_state.current_index = 0
            st.session_state.user_progress = {}
            save_progress(exam_id, {}, st.session_state.exam_config)
            st.rerun()

    with col_b:
        if wrong_stats['total'] > 0:
            st.button("📖 查看错题本", use_container_width=True,
                      help=f"有{wrong_stats['total']}道错题需要复习")
        else:
            st.button("📖 查看错题本", disabled=True, use_container_width=True)

    with col_c:
        if st.button("🏠 返回首页", use_container_width=True, type="secondary"):
            for key in ["exam_started", "selected_types", "current_index", "user_progress",
                        "filtered_questions", "all_questions", "exam_config"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

# 检查是否有题库文件
if not st.session_state.available_exam_files:
    st.error("""
    ❌ 未找到任何 .xlsx 题库文件！
    请将题库文件(.xlsx)放在应用目录下
    """)
    st.stop()