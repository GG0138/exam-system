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
st.title("📚 智能考试系统（多题库 · 断点续答）")


# ================== 工具函数：进度保存/加载 ==================
def get_progress_filename(exam_id):
    """生成进度文件名"""
    # 创建进度保存目录
    progress_dir = "progress_data"
    if not os.path.exists(progress_dir):
        os.makedirs(progress_dir)

    # 使用MD5哈希避免特殊字符问题
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

            # 检查进度文件是否过期（超过7天）
            if "timestamp" in data:
                file_time = datetime.fromisoformat(data["timestamp"])
                if (datetime.now() - file_time).days > 7:
                    st.warning("检测到过期的进度文件（超过7天），将重新开始")
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


# ================== 工具函数：保存/读取 localStorage（备用） ==================
def save_to_local_storage(key, value):
    """将数据保存到浏览器 localStorage（客户端）"""
    js = f"""
    <script>
    try {{
        localStorage.setItem({json.dumps(key)}, {json.dumps(json.dumps(value))});
    }} catch(e) {{
        console.log("localStorage error:", e);
    }}
    </script>
    """
    components.html(js, height=0, width=0)


# ================== 判分函数 ==================
def normalize_answer(answer):
    """标准化答案字符串"""
    if not answer:
        return ""

    answer = str(answer).strip()

    # 处理判断题的各种表示
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

    # 标准化用户输入
    user_norm = normalize_answer(user_input)

    if q_type == "单选":
        # 提取用户选择的标签（A, B, C, D 或 1, 2, 3, 4）
        user_match = re.match(r'^[\(（]?([A-Da-d1-4])[\)）]?[\.．:\s]*', user_input)
        correct_match = re.match(r'^[\(（]?([A-Da-d1-4])[\)）]?[\.．:\s]*', correct_disp)

        if user_match and correct_match:
            # 比较选项标签
            return user_match.group(1).upper() == correct_match.group(1).upper()
        else:
            # 直接比较完整答案
            return user_norm == normalize_answer(correct_disp)

    elif q_type == "判断":
        return user_norm == correct_norm

    elif q_type == "填空":
        # 填空题：完全匹配
        return user_norm == normalize_answer(correct_disp)

    elif q_type == "简答":
        # 简答题：去除空格和标点后比较，允许一定容错
        import unicodedata

        def normalize_text(text):
            # 转换为NFKC形式（全角转半角等）
            text = unicodedata.normalize('NFKC', text)
            # 移除所有空格、标点符号
            text = re.sub(r'[\s\p{P}\p{S}]+', '', text, flags=re.UNICODE)
            return text.lower()

        user_clean = normalize_text(user_input)
        correct_clean = normalize_text(correct_disp)

        # 简答题允许90%相似度
        similarity = 0
        if len(correct_clean) > 0:
            # 简单相似度计算
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, user_clean, correct_clean).ratio()

        return similarity >= 0.9  # 90%相似度即为正确

    return False


# ================== 初始化状态 ==================
if "available_exam_files" not in st.session_state:
    # 自动扫描所有 .xlsx 文件作为题库
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, "data")

    # 优先检查data目录，然后检查当前目录
    xlsx_files = []
    if os.path.exists(data_dir):
        xlsx_files = [f for f in os.listdir(data_dir) if f.endswith(".xlsx")]

    if not xlsx_files:  # 如果没有data目录或目录为空，检查当前目录
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
    """从Excel文件加载题库"""
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            # 尝试在data目录下查找
            data_path = os.path.join("data", file_path)
            if os.path.exists(data_path):
                file_path = data_path
            else:
                st.error(f"❌ 找不到题库文件: {file_path}")
                return []

        # 读取Excel文件
        sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')

        if not sheets:
            st.error("❌ Excel文件为空或格式不正确")
            return []

        all_questions = []
        for sheet_name, df in sheets.items():
            # 检查必要的列
            if "题目" not in df.columns or "正确答案" not in df.columns:
                st.warning(f"⚠️ 工作表 '{sheet_name}' 缺少'题目'或'正确答案'列，已跳过")
                continue

            for idx, row in df.iterrows():
                try:
                    question = str(row["题目"]).strip()
                    if not question:  # 跳过空题目
                        continue

                    correct_ans = str(row["正确答案"]).strip()
                    option_col = row.get("选项", "")
                    explicit_type = row.get("题型", None)
                    explanation = row.get("解析", "")

                    # 处理选项
                    options = []
                    if pd.notna(option_col) and str(option_col).strip():
                        lines = str(option_col).strip().splitlines()
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue

                            # 匹配 A. 选项内容 或 A) 选项内容
                            match = re.match(r'^[\(（]?([A-Da-d1-4])[\)）]?[\.．:\s]', line)
                            if match:
                                label = match.group(1).upper()
                                text = line[match.end():].strip()
                                options.append({"label": label, "text": text})
                            else:
                                options.append({"label": "", "text": line})

                    # 判断题型
                    is_judgment = lambda x: normalize_answer(x) in ["对", "错"]

                    if explicit_type and str(explicit_type).strip() in ["判断", "单选", "填空", "简答"]:
                        q_type = str(explicit_type).strip()
                    elif is_judgment(correct_ans):
                        q_type = "判断"
                    elif options:
                        q_type = "单选"
                    else:
                        q_type = "填空"

                    # 标准化答案
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
                        "row_index": idx + 2  # Excel行号（从2开始）
                    })

                except Exception as e:
                    st.warning(f"⚠️ 处理第{idx + 2}行时出错: {e}")
                    continue

        if not all_questions:
            st.error("❌ 没有成功加载任何题目，请检查Excel文件格式")

        return all_questions

    except ImportError as e:
        st.error(f"❌ 缺少依赖库: {e}")
        st.info("请确保已安装 openpyxl: pip install openpyxl")
        return []
    except Exception as e:
        st.error(f"❌ 加载题库失败: {e}")
        st.info("""
        可能的原因：
        1. 文件不是有效的Excel格式
        2. 文件被其他程序占用
        3. 文件损坏
        4. 缺少'题目'或'正确答案'列
        """)
        return []


# ================== 主流程 ==================
# 侧边栏：系统信息
with st.sidebar:
    st.header("ℹ️ 系统信息")
    st.write(f"Python版本: {sys.version.split()[0]}")
    st.write(f"Pandas版本: {pd.__version__}")

    if st.session_state.get("exam_config"):
        exam_id = st.session_state.exam_config.get("exam_id", "unknown")
        st.write(f"当前题库: {exam_id}")

        if st.button("🧹 清除当前进度", type="secondary"):
            if clear_progress(exam_id):
                st.session_state.user_progress = {}
                st.session_state.current_index = 0
                st.success("进度已清除")
                st.rerun()

    st.divider()
    st.caption("📌 使用说明")
    st.info("""
    1. 选择题库文件
    2. 选择要练习的题型
    3. 逐题作答
    4. 可随时暂停，进度会自动保存
    """)

# 检查是否有题库文件
if not st.session_state.available_exam_files:
    st.error("""
    ❌ 未找到任何 .xlsx 题库文件！

    请按以下方式提供题库文件：
    1. 在应用同目录下放置 .xlsx 文件
    2. 或在应用目录下创建 'data' 文件夹，将题库放入其中

    题库文件要求：
    - Excel格式 (.xlsx)
    - 必须包含'题目'和'正确答案'两列
    - 可选列：'选项'、'题型'、'解析'
    """)
    st.stop()

# 步骤1：选择题库
if not st.session_state.selected_exam_file:
    st.header("📂 请选择题库")

    selected = st.selectbox(
        "可用题库：",
        st.session_state.available_exam_files,
        index=0
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ 使用此题库", type="primary", use_container_width=True):
            st.session_state.selected_exam_file = selected
            st.rerun()

    with col2:
        if st.button("🔄 重新扫描题库", use_container_width=True):
            # 重新扫描文件
            current_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(current_dir, "data")
            xlsx_files = []
            if os.path.exists(data_dir):
                xlsx_files = [f for f in os.listdir(data_dir) if f.endswith(".xlsx")]
            if not xlsx_files:
                xlsx_files = [f for f in os.listdir(".") if f.endswith(".xlsx")]
            st.session_state.available_exam_files = sorted(xlsx_files)
            st.rerun()

# 步骤2：加载题库并选择题型
if st.session_state.selected_exam_file and not st.session_state.exam_started:
    file_path = st.session_state.selected_exam_file
    st.success(f"✅ 已选择题库：**{file_path}**")

    # 生成唯一考试ID
    exam_id = os.path.splitext(file_path)[0]

    # 尝试加载之前保存的进度
    saved_progress, saved_config = load_progress(exam_id)

    # 加载题目
    with st.spinner("正在加载题库，请稍候..."):
        questions = load_questions_from_file(file_path)

    if not questions:
        st.error(f"❌ 无法加载题库 '{file_path}'，请检查文件格式")
        if st.button("↩️ 返回题库选择"):
            st.session_state.selected_exam_file = None
            st.rerun()
        st.stop()

    # 统计题型
    type_counts = {}
    for q in questions:
        t = q["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    st.write(f"📊 共 {len(questions)} 道题目")

    # 显示题型统计
    cols = st.columns(min(4, len(type_counts)))
    for i, (qtype, count) in enumerate(type_counts.items()):
        with cols[i % len(cols)]:
            st.metric(label=f"{qtype}题", value=count)

    st.markdown("---")
    st.subheader("🎯 选择练习模式")

    # 如果有保存的进度，提供恢复选项
    if saved_progress:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🆕 开始新练习", type="primary", use_container_width=True):
                st.session_state.all_questions = questions
                st.session_state.exam_config = {"exam_id": exam_id}
                st.session_state.user_progress = {}
                st.session_state.exam_started = True
                # 清除旧进度
                clear_progress(exam_id)
                st.rerun()

        with col_b:
            if st.button("🔄 继续上次练习", type="secondary", use_container_width=True):
                st.session_state.all_questions = questions
                st.session_state.exam_config = {"exam_id": exam_id}
                st.session_state.user_progress = saved_progress
                st.session_state.exam_started = True

                # 计算已完成题目
                completed = len([v for v in saved_progress.values() if v.get("answer")])
                st.info(f"恢复进度：已完成 {completed} 题")
                st.rerun()
    else:
        if st.button("🚀 开始新练习", type="primary", use_container_width=True):
            st.session_state.all_questions = questions
            st.session_state.exam_config = {"exam_id": exam_id}
            st.session_state.user_progress = {}
            st.session_state.exam_started = True
            st.rerun()

# 步骤3：选择题型（仅在新练习时）
if st.session_state.exam_started and "selected_types" not in st.session_state:
    questions = st.session_state.all_questions

    st.header("🎯 请选择要练习的题型")

    # 统计题型
    type_counts = {}
    for q in questions:
        t = q["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # 题型选择
    selected_types = []
    col1, col2, col3, col4 = st.columns(4)

    type_columns = {"判断": col1, "单选": col2, "填空": col3, "简答": col4}

    for qtype, display_name in [("判断", "判断题"), ("单选", "单选题"), ("填空", "填空题"), ("简答", "简答题")]:
        if qtype in type_counts:
            with type_columns[qtype]:
                if st.checkbox(f"{display_name}\n({type_counts[qtype]}题)", value=True, key=f"type_{qtype}"):
                    selected_types.append(qtype)

    # 全选/全不选
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("全选", use_container_width=True):
            selected_types = list(type_counts.keys())
            st.rerun()
    with col_b:
        if st.button("全不选", use_container_width=True):
            selected_types = []
            st.rerun()

    st.divider()

    # 题目数量设置
    total_selected = sum(type_counts.get(t, 0) for t in selected_types)
    st.write(f"📈 已选择 {len(selected_types)} 种题型，共 {total_selected} 题")

    if total_selected > 0:
        # 限制题目数量
        max_questions = st.slider("最大题目数量", 1, total_selected,
                                  min(50, total_selected),
                                  help="如果题目太多，可以限制练习数量")

        if st.button("🚀 开始答题", type="primary"):
            if not selected_types:
                st.warning("⚠️ 请至少选择一种题型！")
            else:
                # 筛选题目
                filtered = []
                for q in questions:
                    if q["type"] in selected_types:
                        filtered.append({**q, "filtered_index": len(filtered)})

                # 限制题目数量
                if len(filtered) > max_questions:
                    import random

                    random.seed(42)  # 固定随机种子，确保每次选择相同
                    filtered = random.sample(filtered, max_questions)
                    filtered.sort(key=lambda x: x["original_index"])

                st.session_state.filtered_questions = filtered
                st.session_state.current_index = 0
                st.session_state.selected_types = selected_types
                st.session_state.exam_config.update({
                    "selected_types": selected_types,
                    "total": len(filtered),
                    "max_questions": max_questions
                })

                # 保存配置
                exam_id = st.session_state.exam_config["exam_id"]
                save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config)

                st.success(f"已选择 {len(filtered)} 道题目，开始答题！")
                st.rerun()
    else:
        st.warning("请至少选择一种题型")

# 步骤4：逐题答题
if (st.session_state.exam_started and
        "selected_types" in st.session_state and
        st.session_state.current_index < len(st.session_state.filtered_questions)):

    questions = st.session_state.filtered_questions
    idx = st.session_state.current_index
    q = questions[idx]
    exam_id = st.session_state.exam_config["exam_id"]

    # 显示进度条
    progress = (idx + 1) / len(questions)
    st.progress(progress, text=f"进度: {idx + 1}/{len(questions)}")

    # 显示题目
    st.header(f"📝 第 {idx + 1} 题 / 共 {len(questions)} 题")

    # 题目区域
    question_container = st.container()
    with question_container:
        st.subheader(q["question"])
        st.caption(f"题型：{q['type']} | 来源：{q['source']} | 编号：{q['row_index']}")

    # 获取用户之前的答案
    previous_answer = st.session_state.user_progress.get(q["original_index"], {}).get("answer", "")
    input_key = f"input_{exam_id}_{q['original_index']}_{idx}"

    # 答题区域
    st.divider()
    st.subheader("✍️ 请作答：")

    user_ans = None

    if q["type"] == "单选":
        if q["options"]:
            # 构建选项列表
            choices = []
            for opt in q["options"]:
                if opt['label']:
                    choices.append(f"{opt['label']}. {opt['text']}")
                else:
                    choices.append(opt["text"])

            # 如果有之前的答案，找到对应的索引
            default_index = None
            if previous_answer:
                for i, choice in enumerate(choices):
                    if choice.startswith(previous_answer.split('.')[0] if '.' in previous_answer else previous_answer):
                        default_index = i
                        break

            selected = st.radio(
                "请选择：",
                choices,
                index=default_index,
                key=input_key
            )
            user_ans = selected
        else:
            # 如果没有预定义选项，使用文本输入
            user_ans = st.text_input("请输入答案：", value=previous_answer or "", key=input_key)

    elif q["type"] == "判断":
        # 如果有之前的答案，设置默认值
        default_index = 0 if previous_answer == "对" else 1 if previous_answer == "错" else None
        choice = st.radio(
            "请判断：",
            ["✅ 对", "❌ 错"],
            index=default_index,
            key=input_key,
            horizontal=True
        )
        user_ans = "对" if choice == "✅ 对" else "错" if choice == "❌ 错" else None

    elif q["type"] == "填空":
        user_ans = st.text_input("请输入答案：", value=previous_answer or "", key=input_key)

    elif q["type"] == "简答":
        st.info("💡 简答题要求与标准答案基本一致（允许微小差异）")
        user_ans = st.text_area(
            "请输入答案：",
            value=previous_answer or "",
            height=150,
            key=input_key,
            placeholder="请在此输入详细答案..."
        )

    st.divider()

    # 操作按钮
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        submit_disabled = user_ans is None or str(user_ans).strip() == ""
        if st.button("✅ 提交答案", type="primary", disabled=submit_disabled, use_container_width=True):
            is_correct = check_answer(user_ans, q)

            # 保存答题记录
            record = {
                "answer": user_ans,
                "correct": is_correct,
                "time": datetime.now().isoformat(),
                "question": q["question"],
                "correct_answer": q["correct_answer_display"],
                "explanation": q.get("explanation", ""),
                "question_type": q["type"]
            }
            st.session_state.user_progress[q["original_index"]] = record

            # 保存进度到本地文件
            save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config)

            # 显示反馈
            st.divider()
            st.subheader("📊 答案反馈")

            if is_correct:
                st.success("🎉 回答正确！")
            else:
                st.error("❌ 回答错误")

            # 显示用户答案和正确答案
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**你的答案：**")
                if q["type"] == "判断":
                    display_ans = "✅ 对" if user_ans == "对" else "❌ 错" if user_ans == "错" else user_ans
                else:
                    display_ans = user_ans
                st.info(display_ans)

            with col_b:
                st.write("**正确答案：**")
                if q["type"] == "判断":
                    correct_display = "✅ 对" if q["correct_answer_normalized"] == "对" else "❌ 错"
                else:
                    correct_display = q["correct_answer_display"]
                st.success(correct_display)

            # 显示解析（如果有）
            if q.get("explanation"):
                st.write("**解析：**")
                st.info(q["explanation"])

            # 自动跳转到下一题的按钮
            st.divider()
            if st.button("➡️ 下一题", type="primary", use_container_width=True):
                st.session_state.current_index += 1
                st.rerun()

    with col2:
        if st.button("⏭ 跳过本题", use_container_width=True):
            st.session_state.current_index += 1
            st.rerun()

    with col3:
        if idx > 0 and st.button("⬅️ 上一题", use_container_width=True):
            st.session_state.current_index -= 1
            st.rerun()

    with col4:
        if st.button("⏸ 保存并暂停", type="secondary", use_container_width=True):
            # 保存当前进度
            if user_ans:
                record = {
                    "answer": user_ans,
                    "correct": False,  # 未批改
                    "time": datetime.now().isoformat(),
                    "question": q["question"],
                    "correct_answer": q["correct_answer_display"]
                }
                st.session_state.user_progress[q["original_index"]] = record

            save_progress(exam_id, st.session_state.user_progress, st.session_state.exam_config)
            st.success("进度已保存！")
            st.info("您可以关闭浏览器，下次打开时可继续练习")
            st.stop()

    # 显示当前统计
    st.divider()
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        answered = len([v for v in st.session_state.user_progress.values()
                        if v.get("answer") and v.get("correct") is not False])
        st.metric("已答题", f"{answered}/{len(questions)}")

    with col_stat2:
        correct_count = len([v for v in st.session_state.user_progress.values()
                             if v.get("correct", False)])
        accuracy = correct_count / answered * 100 if answered > 0 else 0
        st.metric("正确率", f"{accuracy:.1f}%")

    with col_stat3:
        remaining = len(questions) - idx - 1
        st.metric("剩余题目", remaining)

# 步骤5：练习完成
if (st.session_state.exam_started and
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

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总题数", total)
    with col2:
        st.metric("已答题", answered)
    with col3:
        st.metric("正确数", correct)
    with col4:
        st.metric("正确率", f"{accuracy:.1f}%")

    # 显示各题型统计
    st.subheader("📈 各题型表现")
    type_stats = {}
    for q in questions:
        q_type = q["type"]
        if q_type not in type_stats:
            type_stats[q_type] = {"total": 0, "correct": 0}

        type_stats[q_type]["total"] += 1
        progress = st.session_state.user_progress.get(q["original_index"], {})
        if progress.get("correct", False):
            type_stats[q_type]["correct"] += 1

    for q_type, stats in type_stats.items():
        type_correct = stats["correct"]
        type_total = stats["total"]
        type_accuracy = type_correct / type_total * 100 if type_total > 0 else 0

        st.write(f"**{q_type}题**: {type_correct}/{type_total} ({type_accuracy:.1f}%)")
        st.progress(type_correct / type_total if type_total > 0 else 0)

    # 操作按钮
    st.divider()
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🔄 重新练习", use_container_width=True):
            st.session_state.current_index = 0
            st.session_state.user_progress = {}
            save_progress(exam_id, {}, st.session_state.exam_config)
            st.rerun()

    with col_b:
        if st.button("📊 查看错题", use_container_width=True):
            # 切换到错题模式
            wrong_questions = []
            for q in questions:
                progress = st.session_state.user_progress.get(q["original_index"], {})
                if not progress.get("correct", True):  # 错误或未作答
                    wrong_questions.append(q)

            if wrong_questions:
                st.session_state.filtered_questions = wrong_questions
                st.session_state.current_index = 0
                st.success(f"找到 {len(wrong_questions)} 道错题，开始复习！")
                st.rerun()
            else:
                st.warning("没有错题！")

    with col_c:
        if st.button("🏠 返回首页", type="primary", use_container_width=True):
            # 清除进度文件
            clear_progress(exam_id)
            # 重置session state
            for key in ["exam_started", "selected_types", "current_index", "user_progress",
                        "filtered_questions", "all_questions", "exam_config"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # 显示详细信息
    with st.expander("📋 查看答题详情"):
        for i, q in enumerate(questions):
            progress = st.session_state.user_progress.get(q["original_index"], {})
            if progress:
                col1, col2, col3 = st.columns([6, 2, 2])
                with col1:
                    st.write(f"**{i + 1}. {q['question'][:50]}...**")
                with col2:
                    status = "✅" if progress.get("correct", False) else "❌"
                    st.write(status)
                with col3:
                    if st.button("查看", key=f"detail_{i}"):
                        st.write(f"**题目：** {q['question']}")
                        st.write(f"**你的答案：** {progress.get('answer', '未作答')}")
                        st.write(f"**正确答案：** {q['correct_answer_display']}")
                        if q.get("explanation"):
                            st.write(f"**解析：** {q['explanation']}")