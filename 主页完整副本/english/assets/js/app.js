
        // 校验题库是否加载成功
        if (typeof rawQuestionBank === "undefined" || !Array.isArray(rawQuestionBank) || rawQuestionBank.length === 0) {
            document.body.innerHTML = '<div style="text-align:center;padding:60px 20px;font-family:sans-serif;"><h2 style="color:#ef4444;">⚠️ 题库加载失败</h2><p>未找到 <code>questions.js</code> 文件或文件内容为空。</p><p>请确保 <code>questions.js</code> 与 <code>index.html</code> 在同一目录下。</p></div>';
            throw new Error("questions.js 未加载或为空");
        }

        // --- 全局状态管理 ---
        const AppState = {
            status: [], // 0:未做, 1:正确, 2:错误
            mistakeCount: 0,
            
            // 当前会话状态
            currentMode: 'random', // random, sequential, review
            practiceQueue: [], // 待刷题目索引数组
            currentQueueIndex: 0,
            isAnswered: false,
            currentOptions: [], // 存储当前题目选项，用于键盘映射
            autoAdvance: true, // 自动切题
            autoAdvanceTimer: null
        };

        // --- 初始化与本地存储 ---
        function initApp() {
            try {
                // 加载主题
                if(safeGetStorage('theme') === 'dark') {
                    document.body.setAttribute('data-theme', 'dark');
                }

                // 加载进度
                const savedStatus = safeGetStorage('eng_quiz_status');
                if (savedStatus) {
                    try {
                        AppState.status = JSON.parse(savedStatus);
                    } catch (e) {
                        AppState.status = new Array(rawQuestionBank.length).fill(0);
                    }
                    if(AppState.status.length !== rawQuestionBank.length) {
                        AppState.status = new Array(rawQuestionBank.length).fill(0);
                    }
                } else {
                    AppState.status = new Array(rawQuestionBank.length).fill(0);
                }

                // 加载自动切题设置
                const savedAutoAdvance = safeGetStorage('eng_auto_advance');
                if (savedAutoAdvance !== null) {
                    AppState.autoAdvance = (savedAutoAdvance === 'true');
                }
                document.getElementById('auto-advance-toggle').checked = AppState.autoAdvance;
                
                updateStatsView();
                setupKeyboardListener();
                registerServiceWorker();
                showWelcomeIfNeeded();
            } catch (err) {
                console.error('应用初始化失败:', err);
                showToast('应用加载出现问题，请刷新页面重试。', 'error', 5000);
            }
        }

        // --- 首次欢迎弹窗 ---
        function showWelcomeIfNeeded() {
            if (safeGetStorage('eng_welcome_dismissed') !== 'true') {
                const overlay = document.getElementById('welcome-overlay');
                if (overlay) overlay.classList.add('show');
            }
        }

        function dismissWelcome() {
            const overlay = document.getElementById('welcome-overlay');
            if (overlay) overlay.classList.remove('show');
            safeSetStorage('eng_welcome_dismissed', 'true');
        }

        // --- PWA Service Worker 注册 ---
        function registerServiceWorker() {
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('sw.js').catch(() => {});
            }
        }

        function saveProgress() {
            safeSetStorage('eng_quiz_status', JSON.stringify(AppState.status));
            updateStatsView();
        }

        function toggleAutoAdvance() {
            AppState.autoAdvance = document.getElementById('auto-advance-toggle').checked;
            safeSetStorage('eng_auto_advance', AppState.autoAdvance);
        }

        // --- 核心逻辑 ---

        function startPractice(mode) {
            AppState.currentMode = mode;
            AppState.practiceQueue = generateQueue(mode);
            
            if (AppState.practiceQueue.length === 0) {
                if(mode === 'review') {
                    showToast("太棒了！你目前没有错题记录！", "success");
                } else {
                    showToast("所有题目已完成！建议重置进度或复习错题。", "info");
                }
                return;
            }

            AppState.currentQueueIndex = 0;
            clearAutoAdvanceTimer();
            switchView('quiz');
            loadQuestion();
        }

        function generateQueue(mode) {
            let indices = [];
            if (mode === 'review') {
                // 筛选出错题 (status == 2)
                rawQuestionBank.forEach((_, idx) => {
                    if (AppState.status[idx] === 2) indices.push(idx);
                });
                shuffleArray(indices); // 错题也要乱序
            } else if (mode === 'sequential') {
                // 顺序模式：找出所有未做(0) 或 错误(2) 的题目，按顺序
                rawQuestionBank.forEach((_, idx) => {
                    if (AppState.status[idx] !== 1) indices.push(idx); // 已掌握的(1)就不推了，除非重置
                });
            } else {
                // 随机模式
                rawQuestionBank.forEach((_, idx) => indices.push(idx));
                shuffleArray(indices);
            }
            return indices;
        }

        function loadQuestion() {
            // 检查是否结束
            if (AppState.currentQueueIndex >= AppState.practiceQueue.length) {
                showToast("本轮练习完成！", "success");
                exitPractice();
                return;
            }

            const realIndex = AppState.practiceQueue[AppState.currentQueueIndex];
            const questionData = rawQuestionBank[realIndex];
            AppState.isAnswered = false;
            clearAutoAdvanceTimer();

            // UI 更新
            document.getElementById('current-index-display').innerText = `${realIndex + 1} / ${rawQuestionBank.length}`;
            document.getElementById('remaining-count').innerText = AppState.practiceQueue.length - AppState.currentQueueIndex - 1;
            document.getElementById('mode-badge').innerText = getModeName(AppState.currentMode);
            const progressPct = (AppState.currentQueueIndex / AppState.practiceQueue.length) * 100;
            document.getElementById('session-progress').style.width = `${progressPct}%`;
            // 更新进度条 ARIA
            const progressWrapper = document.querySelector('.progress-wrapper');
            if (progressWrapper) progressWrapper.setAttribute('aria-valuenow', Math.round(progressPct));
            
            // 渲染题目文本 (挖空处理)
            const blankHtml = `<span class="highlight-blank">____</span>`;
            const displayQ = escapeHtml(questionData.question).replace('_____', blankHtml);
            document.getElementById('question-text').innerHTML = displayQ;

            // 渲染选项
            const options = generateOptions(questionData.answer);
            AppState.currentOptions = options; // 存下来用于键盘逻辑
            const optionsContainer = document.getElementById('options-container');
            optionsContainer.innerHTML = '';

            options.forEach((opt, idx) => {
                const btn = document.createElement('button');
                btn.className = 'option-card';
                btn.type = 'button';
                btn.setAttribute('aria-disabled', 'false');
                btn.innerHTML = `<span class="option-key">${idx + 1}</span> <span>${escapeHtml(opt)}</span>`;
                btn.onclick = () => handleAnswer(opt, idx);
                btn.dataset.val = opt;
                btn.id = `opt-${idx}`;
                optionsContainer.appendChild(btn);
            });

            // 隐藏解析
            document.getElementById('analysis-box').style.display = 'none';
            document.getElementById('next-btn').style.display = 'none'; // 答完才显示
            document.getElementById('show-answer-btn').disabled = false;
        }

        function generateOptions(correctAnswer) {
            // 获取所有错误答案
            const allAnswers = [...new Set(rawQuestionBank.map(q => q.answer))];
            const wrongPool = allAnswers.filter(a => a !== correctAnswer);
            
            // 随机选3个错误答案
            shuffleArray(wrongPool);
            const selectedWrong = wrongPool.slice(0, 3);
            
            const options = [correctAnswer, ...selectedWrong];
            shuffleArray(options);
            return options;
        }

        function handleAnswer(selectedVal, domIndex) {
            if (AppState.isAnswered) return;
            AppState.isAnswered = true;

            const realIndex = AppState.practiceQueue[AppState.currentQueueIndex];
            const correctVal = rawQuestionBank[realIndex].answer;
            const isCorrect = selectedVal === correctVal;

            // 更新数据
            AppState.status[realIndex] = isCorrect ? 1 : 2;
            saveProgress();

            // UI 反馈
            const options = document.querySelectorAll('.option-card');
            options.forEach(opt => {
                opt.setAttribute('aria-disabled', 'true');
                if(opt.dataset.val === correctVal) opt.classList.add('correct');
                else if(opt.dataset.val === selectedVal && !isCorrect) opt.classList.add('incorrect');
            });

            // 显示解析
            const analysisBox = document.getElementById('analysis-box');
            document.getElementById('feedback-title').innerHTML = isCorrect ? 
                '<span style="color:var(--success-color)">✓ 回答正确</span>' : 
                '<span style="color:var(--error-color)">✗ 回答错误</span>';
            document.getElementById('translation-text').innerText = rawQuestionBank[realIndex].translation;
            analysisBox.style.display = 'block';
            document.getElementById('next-btn').style.display = 'inline-block';
            document.getElementById('show-answer-btn').disabled = true;

            // 自动切题逻辑
            if(isCorrect && AppState.autoAdvance) {
                // 延时 0.7秒 跳转，让用户看清“绿色”正确反馈
                AppState.autoAdvanceTimer = setTimeout(() => {
                    // 确保用户没有在等待期间手动点了退出
                    if (document.getElementById('quiz-view').style.display !== 'none') {
                        nextQuestion();
                    }
                }, 700); 
            }
        }

        function nextQuestion() {
            if (!AppState.isAnswered) return;
            clearAutoAdvanceTimer();
            AppState.currentQueueIndex++;
            loadQuestion();
        }

        function showAnswer() {
            if (AppState.isAnswered) return;
            // 视为答错，标记错题
            const realIndex = AppState.practiceQueue[AppState.currentQueueIndex];
            AppState.status[realIndex] = 2;
            saveProgress();

            // 直接高亮正确答案并显示解析（不走 handleAnswer 的对错判断）
            AppState.isAnswered = true;
            const correctVal = rawQuestionBank[realIndex].answer;
            const options = document.querySelectorAll('.option-card');
            options.forEach(opt => {
                opt.setAttribute('aria-disabled', 'true');
                if(opt.dataset.val === correctVal) opt.classList.add('correct');
            });

            const analysisBox = document.getElementById('analysis-box');
            document.getElementById('feedback-title').innerHTML =
                '<span style="color:var(--warning-color)">📖 答案已显示</span>';
            document.getElementById('translation-text').innerText = rawQuestionBank[realIndex].translation;
            analysisBox.style.display = 'block';
            document.getElementById('next-btn').style.display = 'inline-block';
            document.getElementById('show-answer-btn').disabled = true;
        }

        // --- 辅助功能 ---

        function updateStatsView() {
            const total = rawQuestionBank.length;
            const done = AppState.status.filter(s => s !== 0).length;
            const correct = AppState.status.filter(s => s === 1).length;
            const wrong = AppState.status.filter(s => s === 2).length;

            document.getElementById('stat-total').innerText = total;
            document.getElementById('stat-done').innerText = done;
            document.getElementById('stat-wrong').innerText = wrong;
            document.getElementById('stat-accuracy').innerText = done > 0 ? Math.round((correct / done) * 100) + '%' : '0%';

            // 进度条
            const doneBar = document.getElementById('stat-done-bar');
            const accBar = document.getElementById('stat-accuracy-bar');
            if (doneBar) doneBar.style.width = `${Math.round((done / total) * 100)}%`;
            if (accBar) accBar.style.width = done > 0 ? `${Math.round((correct / done) * 100)}%` : '0%';

            // 控制错题按钮状态
            document.getElementById('btn-review-mistakes').disabled = (wrong === 0);
        }

        function switchView(viewName) {
            const statsView = document.getElementById('stats-view');
            const quizView = document.getElementById('quiz-view');
            if (viewName === 'stats') {
                statsView.style.display = 'block';
                statsView.classList.add('view-fade-in');
                quizView.style.display = 'none';
                updateStatsView();
            } else {
                quizView.style.display = 'block';
                quizView.classList.add('view-fade-in');
                statsView.style.display = 'none';
            }
            // 动画结束后移除 class，避免重复触发
            setTimeout(() => {
                statsView.classList.remove('view-fade-in');
                quizView.classList.remove('view-fade-in');
            }, 300);
        }

        function exitPractice() {
            clearAutoAdvanceTimer();
            switchView('stats');
        }

        function resetAllProgress() {
            if(confirm('确定要清空所有刷题记录吗？此操作不可恢复。')) {
                AppState.status = new Array(rawQuestionBank.length).fill(0);
                saveProgress();
                showToast("所有进度已重置", "warning");
            }
        }

        function toggleTheme() {
            const body = document.body;
            if (body.getAttribute('data-theme') === 'dark') {
                body.removeAttribute('data-theme');
                safeSetStorage('theme', 'light');
            } else {
                body.setAttribute('data-theme', 'dark');
                safeSetStorage('theme', 'dark');
            }
        }

        function getModeName(mode) {
            const map = { 'random': '随机', 'sequential': '顺序', 'review': '错题' };
            return map[mode] || '练习';
        }

        function shuffleArray(array) {
            for (let i = array.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [array[i], array[j]] = [array[j], array[i]];
            }
        }

        function clearAutoAdvanceTimer() {
            if (AppState.autoAdvanceTimer) {
                clearTimeout(AppState.autoAdvanceTimer);
                AppState.autoAdvanceTimer = null;
            }
        }

        function escapeHtml(value) {
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        function safeGetStorage(key) {
            try {
                return localStorage.getItem(key);
            } catch (e) {
                return null;
            }
        }

        function safeSetStorage(key, value) {
            try {
                localStorage.setItem(key, value);
            } catch (e) {
                console.warn('本地进度保存失败，浏览器可能限制了 localStorage。', e);
            }
        }

        // --- 键盘支持 ---
        function setupKeyboardListener() {
            document.addEventListener('keydown', (e) => {
                // Escape 关闭弹窗（欢迎 > 数据模态框）
                if (e.key === 'Escape') {
                    const welcome = document.getElementById('welcome-overlay');
                    if (welcome && welcome.classList.contains('show')) {
                        dismissWelcome();
                        return;
                    }
                    const modal = document.getElementById('data-modal');
                    if (modal.style.display === 'flex') {
                        closeDataModal();
                        return;
                    }
                }

                if (document.getElementById('quiz-view').style.display === 'none') return;

                const key = e.key;
                // 选项 1-4
                if (['1', '2', '3', '4'].includes(key)) {
                    const idx = parseInt(key) - 1;
                    const optBtn = document.getElementById(`opt-${idx}`);
                    if (optBtn && !AppState.isAnswered) {
                        optBtn.click();
                    }
                }
                // Enter 下一题
                if (key === 'Enter') {
                    if (AppState.isAnswered) {
                        nextQuestion();
                    }
                }
            });
        }

        // --- 数据导入导出 ---
        function openDataModal() {
            const modal = document.getElementById('data-modal');
            modal.style.display = 'flex';
            modal.classList.add('show');
            const data = {
                status: AppState.status,
                timestamp: new Date().toISOString()
            };
            document.getElementById('data-area').value = JSON.stringify(data);
            modal.querySelector('.btn-secondary').focus();
        }

        function closeDataModal() {
            const modal = document.getElementById('data-modal');
            modal.classList.remove('show');
            modal.style.display = 'none';
        }

        function copyData() {
            const textarea = document.getElementById('data-area');
            textarea.select();
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(textarea.value).then(() => {
                    showToast("已复制到剪贴板！", "success");
                }).catch(() => {
                    document.execCommand('copy');
                    showToast("已复制到剪贴板！", "success");
                });
            } else {
                document.execCommand('copy');
                showToast("已复制到剪贴板！", "success");
            }
        }

        function importData() {
            try {
                const jsonStr = document.getElementById('data-area').value;
                const data = JSON.parse(jsonStr);
                if (Array.isArray(data.status) && data.status.length === rawQuestionBank.length) {
                    AppState.status = data.status;
                    saveProgress();
                    showToast("数据恢复成功！", "success");
                    closeDataModal();
                    updateStatsView();
                } else {
                    showToast("数据格式不正确，无法恢复。", "error");
                }
            } catch (e) {
                showToast("JSON 解析失败，请检查数据格式。", "error");
            }
        }

        // 启动 - 确保 DOM 完全加载后再初始化
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initApp);
        } else {
            initApp();
        }

        // Navigation
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                if (document.querySelector('.welcome-overlay.show')) return;
                if (document.querySelector('.modal-overlay.show, .data-modal.show')) return;
                window.location.href = '../';
            }
        });
    
