import sys
print("已安装的包：", [pkg for pkg in sys.modules if 'openpy' in pkg])
import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="智能考试系统", page_icon="📚")
st.title("📚 智能考试系统（多题库 · 断点续答）")


# ================== 工具函数：保存/读取 localStorage ==================
def save_to_local_storage(key, value):
    """将数据保存到浏览器 localStorage"""
    js = f"""
    <script>
    localStorage.setItem({json.dumps(key)}, {json.dumps(json.dumps(value))});
    </script>
    """
    components.html(js, height=0)


def get_local_storage_key(base_key, exam_id):
    """生成带题库标识的 key，避免冲突"""
    return f"exam_{exam_id}_{base_key}"


# ================== 初始化状态 ==================
if "available_exam_files" not in st.session_state:
    # 自动扫描所有 .xlsx 文件作为题库
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


# ================== 加载指定题库 ==================
@st.cache_resource
def load_questions_from_file(file_path):
    try:
        sheets = pd.read_excel(file_path, sheet_name=None)
        all_questions = []
        for sheet_name, df in sheets.items():
            if "题目" not in df.columns or "正确答案" not in df.columns:
                continue
            for _, row in df.iterrows():
                question = str(row["题目"]).strip()
                correct_ans = str(row["正确答案"]).strip()
                option_col = row.get("选项", "")
                explicit_type = row.get("题型", None)

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

                is_judgment = lambda x: x in ["✅", "❌"]
                q_type = "简答" if explicit_type == "简答" else \
                    "判断" if is_judgment(correct_ans) else \
                        "单选" if options else "填空"

                normalized_ans = "对" if correct_ans == "✅" else "错" if correct_ans == "❌" else correct_ans

                all_questions.append({
                    "original_index": len(all_questions),
                    "question": question,
                    "type": q_type,
                    "options": options,
                    "correct_answer_normalized": normalized_ans,
                    "correct_answer_display": correct_ans,
                    "source": f"{sheet_name}"
                })
        return all_questions
    except Exception as e:
        st.error(f"❌ 加载题库失败：{e}")
        return []


# ================== 主流程 ==================
if not st.session_state.available_exam_files:
    st.error("❌ 未找到任何 .xlsx 题库文件！请上传至少一个 Excel 文件。")
    st.stop()

# 步骤1：选择题库
if not st.session_state.selected_exam_file:
    st.header("📂 请选择题库")
    selected = st.selectbox(
        "可用题库：",
        st.session_state.available_exam_files,
        index=0
    )
    if st.button("✅ 使用此题库"):
        st.session_state.selected_exam_file = selected
        st.rerun()

# 步骤2：加载题库并选择题型
if st.session_state.selected_exam_file and not st.session_state.exam_started:
    file_path = st.session_state.selected_exam_file
    st.success(f"✅ 已选择题库：**{file_path}**")

    # 生成唯一考试ID（用于隔离进度）
    exam_id = os.path.splitext(file_path)[0]  # 如 "math"

    # 尝试从 localStorage 恢复配置
    config_key = get_local_storage_key("config", exam_id)
    progress_key = get_local_storage_key("progress", exam_id)

    # 这里简化：不自动恢复，而是让用户决定是否继续
    # 实际中可通过 JS 读取，但为兼容性，我们提供“继续上次”按钮

    # 加载题目
    questions = load_questions_from_file(file_path)
    if not questions:
        st.stop()

    # 统计题型
    type_counts = {}
    for q in questions:
        t = q["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    st.write(f"📊 共 {len(questions)} 道题目")
    cols = st.columns(len(type_counts))
    for i, (qtype, count) in enumerate(type_counts.items()):
        cols[i].metric(label=qtype, value=count)

    # 是否继续上次？
    st.markdown("---")
    st.subheader("🎯 选择练习模式")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🆕 开始新练习"):
            st.session_state.all_questions = questions
            st.session_state.exam_config = {"exam_id": exam_id}
            st.session_state.user_progress = {}
            st.session_state.exam_started = True
            st.rerun()
    with col_b:
        # 模拟“继续上次”（实际需 JS 读取，此处简化）
        st.button("🔄 继续上次练习（开发中）", disabled=True)
        st.caption("💡 功能将在后续版本完善")

# 步骤3：选择题型（仅在新练习时）
if st.session_state.exam_started and "selected_types" not in st.session_state:
    st.header("🎯 请选择要练习的题型")
    questions = st.session_state.all_questions
    type_counts = {}
    for q in questions:
        t = q["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    selected_types = []
    for qtype in ["判断", "单选", "填空", "简答"]:
        if qtype in type_counts:
            if st.checkbox(f"{qtype}题（{type_counts[qtype]}道）", value=True):
                selected_types.append(qtype)

    if st.button("🚀 开始答题"):
        if not selected_types:
            st.warning("⚠️ 请至少选择一种题型！")
        else:
            filtered = [
                {**q, "filtered_index": i}
                for i, q in enumerate([q for q in questions if q["type"] in selected_types])
            ]
            st.session_state.filtered_questions = filtered
            st.session_state.current_index = 0
            st.session_state.selected_types = selected_types
            st.session_state.exam_config.update({
                "selected_types": selected_types,
                "total": len(filtered)
            })
            # 保存配置（含题库ID）
            exam_id = st.session_state.exam_config["exam_id"]
            save_to_local_storage(get_local_storage_key("config", exam_id), st.session_state.exam_config)
            st.rerun()

# 步骤4：逐题答题
if (st.session_state.exam_started and
        "selected_types" in st.session_state and
        st.session_state.current_index < len(st.session_state.filtered_questions)):

    questions = st.session_state.filtered_questions
    idx = st.session_state.current_index
    q = questions[idx]
    exam_id = st.session_state.exam_config["exam_id"]

    st.header(f"📝 第 {idx + 1} 题 / 共 {len(questions)} 题")
    st.subheader(q["question"])
    st.caption(f"题型：{q['type']} | 来源：{q['source']}")

    user_ans = st.session_state.user_progress.get(q["original_index"], {}).get("answer", None)
    input_key = f"input_{exam_id}_{q['original_index']}"

    # 答题控件
    if q["type"] == "单选":
        if q["options"]:
            choices = [f"{opt['label']}. {opt['text']}" for opt in q["options"] if opt['label']]
            if not choices:  # 无标签选项
                choices = [opt["text"] for opt in q["options"]]
            selected = st.radio("", choices, index=None, key=input_key)
            user_ans = selected
        else:
            user_ans = st.text_input("答案", value=user_ans or "", key=input_key)

    elif q["type"] == "判断":
        choice = st.radio("", ["✅ 对", "❌ 错"], index=None, key=input_key)
        user_ans = "对" if choice == "✅ 对" else "错" if choice == "❌ 错" else None

    elif q["type"] == "填空":
        user_ans = st.text_input("答案", value=user_ans or "", key=input_key)

    elif q["type"] == "简答":
        st.warning("⚠️ 简答题要求一字不差")
        user_ans = st.text_area("请输入完整答案：", value=user_ans or "", height=100, key=input_key)


    # 判分
    def check_answer(user_input, q):
        correct_norm = q["correct_answer_normalized"]
        correct_disp = q["correct_answer_display"]
        q_type = q["type"]
        if q_type == "单选":
            if user_input and "." in user_input:
                user_label = user_input.split(".")[0].strip().upper()
                return user_label == str(correct_disp).strip().upper()
        elif q_type == "判断":
            return str(user_input).strip() == str(correct_norm).strip()
        else:
            return str(user_input).strip() == str(correct_disp).strip()
        return False


    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ 提交并查看解析", use_container_width=True):
            if user_ans is None or str(user_ans).strip() == "":
                st.warning("⚠️ 请先作答！")
            else:
                is_correct = check_answer(user_ans, q)
                record = {
                    "answer": user_ans,
                    "correct": is_correct,
                    "time": datetime.now().isoformat(),
                    "question": q["question"],
                    "correct_answer": q["correct_answer_display"]
                }
                st.session_state.user_progress[q["original_index"]] = record

                # 保存进度（按题库隔离）
                save_to_local_storage(get_local_storage_key("progress", exam_id), st.session_state.user_progress)

                # 显示反馈
                st.divider()
                if is_correct:
                    st.success("🎉 回答正确！")
                else:
                    st.error("❌ 回答错误")
                user_show = (
                    ("✅ 对" if user_ans == "对" else "❌ 错" if user_ans == "错" else "(未作答)")
                    if q["type"] == "判断" else
                    (str(user_ans).strip() if user_ans else "(未作答)")
                )
                st.write(f"**你的答案**：{user_show}")
                st.write(f"**正确答案**：{q['correct_answer_display']}")

                if st.button("➡️ 下一题", use_container_width=True):
                    st.session_state.current_index += 1
                    st.rerun()

    with col2:
        if st.button("⏭ 跳过本题", use_container_width=True):
            st.session_state.current_index += 1
            st.rerun()

# 步骤5：练习完成
if (st.session_state.exam_started and
        "selected_types" in st.session_state and
        st.session_state.current_index >= len(st.session_state.filtered_questions)):

    st.success("🎉 练习完成！")
    total = len(st.session_state.filtered_questions)
    correct = sum(1 for rec in st.session_state.user_progress.values() if rec.get("correct"))
    st.metric("最终得分", f"{correct} / {total}")

    if st.button("🏠 返回首页"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()