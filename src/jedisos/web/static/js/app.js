/**
 * [JS-W010] jedisos.web.static.js.app
 * JediSOS 웹 UI Alpine.js 애플리케이션 로직
 *
 * version: 1.0.0
 * created: 2026-02-18
 * modified: 2026-02-18
 * dependencies: alpinejs@3
 */

/**
 * 메인 Alpine.js 앱 함수.  [JS-W010.1]
 *
 * @returns {Object} Alpine.js 컴포넌트 데이터 및 메서드
 */
function app() {
    return {
        // ──────────────────────────────
        // 네비게이션
        // ──────────────────────────────
        currentPage: 'chat',
        settingsTab: 'apiKeys',
        monitoringTab: 'audit',
        loading: true,

        // 환경변수 입력값 임시 저장
        envValues: {},

        // 토스트 알림
        toast: {
            show: false,
            message: '',
            type: 'success', // 'success' | 'error'
        },

        // ──────────────────────────────
        // Setup 상태
        // ──────────────────────────────
        setup: {
            isFirstRun: true,
            step: 1,
            openaiKey: '',
            googleKey: '',
            telegramToken: '',
            discordToken: '',
            slackBotToken: '',
            slackAppToken: '',
            models: 'gpt-5.2, gemini/gemini-3-flash',
            saving: false,
            showTelegramGuide: false,
            showDiscordGuide: false,
            showSlackGuide: false,
        },

        // ──────────────────────────────
        // 채팅 상태
        // ──────────────────────────────
        chat: {
            messages: [],
            input: '',
            ws: null,
            connected: false,
            sending: false,
        },

        // ──────────────────────────────
        // 설정 상태
        // ──────────────────────────────
        settings: {
            env: [],
            llm: { models: [], temperature: 0.7, max_tokens: 8192, timeout: 60 },
            security: {},
        },

        // ──────────────────────────────
        // 패키지 상태
        // ──────────────────────────────
        packagesTab: 'skills',
        packages: {
            skills: [],
            servers: [],
            recommended: [],
            newServer: { name: '', url: '', description: '' },
        },

        // ──────────────────────────────
        // 모니터링 상태
        // ──────────────────────────────
        monitoring: {
            status: {},
            audit: [],
            denied: [],
            policy: {},
        },

        // ══════════════════════════════
        // 라이프사이클
        // ══════════════════════════════

        /**
         * Alpine.js 초기화.  [JS-W010.2]
         * Setup 상태를 확인하고, 첫 실행이면 Setup Wizard를, 아니면 채팅을 표시합니다.
         */
        async init() {
            try {
                await this.checkSetupStatus();
                if (this.setup.isFirstRun) {
                    this.currentPage = 'setup';
                } else {
                    this.currentPage = 'chat';
                    this.connectWebSocket();
                }
            } catch (e) {
                console.error('초기화 실패:', e);
                this.currentPage = 'chat';
            } finally {
                this.loading = false;
            }
        },

        // ══════════════════════════════
        // 유틸리티
        // ══════════════════════════════

        /**
         * API 호출 헬퍼.  [JS-W010.3]
         *
         * @param {string} method - HTTP 메서드
         * @param {string} url - 요청 URL
         * @param {Object|null} body - 요청 바디
         * @returns {Promise<Object>} 응답 JSON
         */
        async api(method, url, body = null) {
            const opts = {
                method,
                headers: { 'Content-Type': 'application/json' },
            };
            if (body !== null) {
                opts.body = JSON.stringify(body);
            }
            const res = await fetch(url, opts);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${res.status}`);
            }
            return res.json();
        },

        /**
         * 토스트 알림 표시.  [JS-W010.4]
         *
         * @param {string} message - 알림 메시지
         * @param {string} type - 'success' 또는 'error'
         */
        showToast(message, type = 'success') {
            this.toast.message = message;
            this.toast.type = type;
            this.toast.show = true;
            setTimeout(() => {
                this.toast.show = false;
            }, 3000);
        },

        /**
         * 페이지 네비게이션.  [JS-W010.5]
         *
         * @param {string} page - 이동할 페이지 이름
         */
        navigateTo(page) {
            this.currentPage = page;
            if (page === 'chat' && !this.chat.connected) {
                this.connectWebSocket();
            } else if (page === 'settings') {
                this.loadEnvKeys();
                this.loadLLMSettings();
                this.loadSecuritySettings();
            } else if (page === 'packages') {
                this.loadSkills();
                this.loadServers();
                this.loadRecommended();
            } else if (page === 'monitoring') {
                this.loadMonitoring();
            }
        },

        /**
         * 현재 시간 문자열 반환.  [JS-W010.6]
         *
         * @returns {string} HH:MM 형식 시간
         */
        now() {
            return new Date().toLocaleTimeString('ko-KR', {
                hour: '2-digit',
                minute: '2-digit',
            });
        },

        // ══════════════════════════════
        // Setup 메서드
        // ══════════════════════════════

        /**
         * Setup 상태 확인.  [JS-W010.7]
         */
        async checkSetupStatus() {
            try {
                const data = await this.api('GET', '/api/setup/status');
                this.setup.isFirstRun = data.is_first_run;
            } catch (e) {
                console.error('Setup 상태 확인 실패:', e);
                this.setup.isFirstRun = false;
            }
        },

        /**
         * Setup 완료.  [JS-W010.8]
         * Setup Wizard의 모든 정보를 서버에 전송합니다.
         */
        async completeSetup() {
            this.setup.saving = true;
            try {
                await this.api('POST', '/api/setup/complete', {
                    openai_api_key: this.setup.openaiKey,
                    google_api_key: this.setup.googleKey,
                    telegram_bot_token: this.setup.telegramToken,
                    discord_bot_token: this.setup.discordToken,
                    slack_bot_token: this.setup.slackBotToken,
                    slack_app_token: this.setup.slackAppToken,
                    models: this.setup.models.split(',').map(s => s.trim()).filter(Boolean),
                });
                this.showToast('설정이 완료되었습니다');
                this.setup.isFirstRun = false;
                this.currentPage = 'chat';
                this.connectWebSocket();
            } catch (e) {
                this.showToast('설정 저장 실패: ' + e.message, 'error');
            } finally {
                this.setup.saving = false;
            }
        },

        // ══════════════════════════════
        // 채팅 메서드
        // ══════════════════════════════

        /**
         * WebSocket 연결.  [JS-W010.9]
         */
        connectWebSocket() {
            if (this.chat.ws && this.chat.ws.readyState === WebSocket.OPEN) {
                return;
            }

            const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = wsProto + '//' + location.host + '/api/chat/ws';

            try {
                this.chat.ws = new WebSocket(wsUrl);

                this.chat.ws.onopen = () => {
                    this.chat.connected = true;
                    console.log('WebSocket 연결됨');
                };

                this.chat.ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.error) {
                            this.chat.messages.push({
                                role: 'assistant',
                                content: '오류: ' + data.error,
                                time: this.now(),
                            });
                            this.chat.sending = false;
                        } else if (data.type === 'stream') {
                            // 스트리밍: 마지막 assistant 메시지에 토큰 추가
                            const msgs = this.chat.messages;
                            const last = msgs.length > 0 ? msgs[msgs.length - 1] : null;
                            if (last && last.role === 'assistant' && last._streaming) {
                                last.content += data.content;
                            } else {
                                msgs.push({
                                    role: 'assistant',
                                    content: data.content,
                                    time: this.now(),
                                    _streaming: true,
                                });
                            }
                        } else if (data.type === 'done') {
                            // 스트리밍 완료: _streaming 플래그 제거
                            const msgs = this.chat.messages;
                            const last = msgs.length > 0 ? msgs[msgs.length - 1] : null;
                            if (last && last._streaming) {
                                last._streaming = false;
                                last.content = data.response;
                            } else {
                                msgs.push({
                                    role: 'assistant',
                                    content: data.response,
                                    time: this.now(),
                                });
                            }
                            this.chat.sending = false;
                        } else if (data.type === 'notification') {
                            // 백그라운드 작업 완료 알림 (스킬 생성 등)
                            const isError = data.event === 'skill_failed' || data.event === 'skill_error';
                            this.showToast(data.message, isError ? 'error' : 'success');
                            this.chat.messages.push({
                                role: 'assistant',
                                content: data.message,
                                time: this.now(),
                            });
                        } else if (data.response) {
                            // 레거시 호환 (비스트리밍)
                            this.chat.messages.push({
                                role: 'assistant',
                                content: data.response,
                                time: this.now(),
                            });
                            this.chat.sending = false;
                        }
                    } catch (e) {
                        console.error('메시지 파싱 실패:', e);
                        this.chat.sending = false;
                    }
                    this.$nextTick(() => this.scrollToBottom());
                };

                this.chat.ws.onclose = () => {
                    this.chat.connected = false;
                    console.log('WebSocket 연결 끊김, 3초 후 재연결...');
                    setTimeout(() => {
                        if (this.currentPage === 'chat') {
                            this.connectWebSocket();
                        }
                    }, 3000);
                };

                this.chat.ws.onerror = (err) => {
                    console.error('WebSocket 오류:', err);
                    this.chat.connected = false;
                };
            } catch (e) {
                console.error('WebSocket 연결 실패:', e);
                this.chat.connected = false;
            }
        },

        /**
         * 메시지 전송.  [JS-W010.10]
         */
        sendMessage() {
            const text = this.chat.input.trim();
            if (!text || !this.chat.connected || this.chat.sending) {
                return;
            }

            // 사용자 메시지 추가
            this.chat.messages.push({
                role: 'user',
                content: text,
                time: this.now(),
            });
            this.chat.input = '';
            this.chat.sending = true;

            // WebSocket으로 전송
            try {
                this.chat.ws.send(JSON.stringify({
                    message: text,
                    bank_id: 'default',
                }));
            } catch (e) {
                this.chat.sending = false;
                this.showToast('메시지 전송 실패', 'error');
            }

            this.$nextTick(() => this.scrollToBottom());
        },

        /**
         * WebSocket 연결 해제.  [JS-W010.11]
         */
        disconnectWebSocket() {
            if (this.chat.ws) {
                this.chat.ws.close();
                this.chat.ws = null;
                this.chat.connected = false;
            }
        },

        /**
         * 채팅 영역 하단으로 스크롤.  [JS-W010.12]
         */
        scrollToBottom() {
            const el = this.$refs.chatMessages;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        },

        // ══════════════════════════════
        // 설정 메서드
        // ══════════════════════════════

        /**
         * 환경변수 키 목록 로드.  [JS-W010.13]
         */
        async loadEnvKeys() {
            try {
                const data = await this.api('GET', '/api/settings/env');
                this.settings.env = data.configured || [];
                // 입력값 초기화
                this.settings.env.forEach((e) => {
                    if (!this.envValues[e.key]) {
                        this.envValues[e.key] = '';
                    }
                });
            } catch (e) {
                console.error('환경변수 로드 실패:', e);
            }
        },

        /**
         * 환경변수 저장.  [JS-W010.14]
         *
         * @param {string} key - 환경변수 키
         * @param {string} value - 환경변수 값
         */
        async saveEnvVar(key, value) {
            if (!value || !value.trim()) {
                this.showToast('값을 입력하세요', 'error');
                return;
            }
            try {
                await this.api('PUT', '/api/settings/env', { key, value: value.trim() });
                this.showToast(key + ' 저장 완료');
                this.envValues[key] = '';
                await this.loadEnvKeys();
            } catch (e) {
                this.showToast('저장 실패: ' + e.message, 'error');
            }
        },

        /**
         * LLM 설정 로드.  [JS-W010.15]
         */
        async loadLLMSettings() {
            try {
                const data = await this.api('GET', '/api/settings/llm');
                this.settings.llm = {
                    models: data.models || [],
                    temperature: data.temperature ?? 0.7,
                    max_tokens: data.max_tokens ?? 8192,
                    timeout: data.timeout ?? 60,
                };
            } catch (e) {
                console.error('LLM 설정 로드 실패:', e);
            }
        },

        /**
         * LLM 설정 저장.  [JS-W010.16]
         */
        async saveLLMSettings() {
            try {
                await this.api('PUT', '/api/settings/llm', {
                    models: this.settings.llm.models.filter((m) => m.trim()),
                    temperature: this.settings.llm.temperature,
                    max_tokens: this.settings.llm.max_tokens,
                    timeout: this.settings.llm.timeout,
                });
                this.showToast('LLM 설정 저장 완료');
            } catch (e) {
                this.showToast('LLM 설정 저장 실패: ' + e.message, 'error');
            }
        },

        /**
         * 보안 설정 로드.  [JS-W010.17]
         */
        async loadSecuritySettings() {
            try {
                const data = await this.api('GET', '/api/settings/security');
                this.settings.security = data;
            } catch (e) {
                console.error('보안 설정 로드 실패:', e);
            }
        },

        // ══════════════════════════════
        // 패키지 메서드 (Skills + MCP)
        // ══════════════════════════════

        /**
         * Skill 목록 로드.  [JS-W010.24]
         */
        async loadSkills() {
            try {
                const data = await this.api('GET', '/api/skills/');
                this.packages.skills = data.skills || [];
            } catch (e) {
                console.error('Skill 목록 로드 실패:', e);
            }
        },

        /**
         * Skill 삭제.  [JS-W010.25]
         *
         * @param {string} name - Skill 이름
         */
        async removeSkill(name) {
            if (!confirm(name + ' Skill을 삭제하시겠습니까?')) {
                return;
            }
            try {
                await this.api('DELETE', '/api/skills/' + encodeURIComponent(name));
                this.showToast(name + ' Skill 삭제 완료');
                await this.loadSkills();
            } catch (e) {
                this.showToast('Skill 삭제 실패: ' + e.message, 'error');
            }
        },

        /**
         * Skill 토글 (활성/비활성).  [JS-W010.26]
         *
         * @param {string} name - Skill 이름
         */
        async toggleSkill(name) {
            try {
                await this.api('PUT', '/api/skills/' + encodeURIComponent(name) + '/toggle');
                await this.loadSkills();
            } catch (e) {
                this.showToast('Skill 토글 실패: ' + e.message, 'error');
            }
        },

        /**
         * 설치된 서버 목록 로드.  [JS-W010.18]
         */
        async loadServers() {
            try {
                const data = await this.api('GET', '/api/mcp/servers');
                this.packages.servers = data.servers || [];
            } catch (e) {
                console.error('서버 목록 로드 실패:', e);
            }
        },

        /**
         * 새 MCP 서버 설치.  [JS-W010.19]
         */
        async installServer() {
            const { name, url, description } = this.packages.newServer;
            if (!name || !url) {
                this.showToast('서버 이름과 URL을 입력하세요', 'error');
                return;
            }
            try {
                await this.api('POST', '/api/mcp/servers', { name, url, description });
                this.showToast(name + ' 서버 추가 완료');
                this.packages.newServer = { name: '', url: '', description: '' };
                await this.loadServers();
            } catch (e) {
                this.showToast('서버 추가 실패: ' + e.message, 'error');
            }
        },

        /**
         * MCP 서버 삭제.  [JS-W010.20]
         *
         * @param {string} name - 서버 이름
         */
        async removeServer(name) {
            if (!confirm(name + ' 서버를 삭제하시겠습니까?')) {
                return;
            }
            try {
                await this.api('DELETE', '/api/mcp/servers/' + encodeURIComponent(name));
                this.showToast(name + ' 서버 삭제 완료');
                await this.loadServers();
            } catch (e) {
                this.showToast('서버 삭제 실패: ' + e.message, 'error');
            }
        },

        /**
         * MCP 서버 토글 (활성/비활성).  [JS-W010.21]
         *
         * @param {string} name - 서버 이름
         */
        async toggleServer(name) {
            try {
                await this.api('PUT', '/api/mcp/servers/' + encodeURIComponent(name) + '/toggle');
                await this.loadServers();
            } catch (e) {
                this.showToast('서버 토글 실패: ' + e.message, 'error');
            }
        },

        /**
         * 추천 서버 목록 로드.  [JS-W010.22]
         */
        async loadRecommended() {
            try {
                const data = await this.api('GET', '/api/setup/recommended-mcp');
                this.packages.recommended = data.servers || [];
            } catch (e) {
                console.error('추천 서버 로드 실패:', e);
            }
        },

        // ══════════════════════════════
        // 모니터링 메서드
        // ══════════════════════════════

        /**
         * 모니터링 데이터 전체 로드.  [JS-W010.23]
         */
        async loadMonitoring() {
            try {
                const [statusRes, auditRes, deniedRes, policyRes] = await Promise.allSettled([
                    this.api('GET', '/api/monitoring/status'),
                    this.api('GET', '/api/monitoring/audit'),
                    this.api('GET', '/api/monitoring/audit/denied'),
                    this.api('GET', '/api/monitoring/policy'),
                ]);

                if (statusRes.status === 'fulfilled') {
                    this.monitoring.status = statusRes.value;
                }
                if (auditRes.status === 'fulfilled') {
                    this.monitoring.audit = auditRes.value.entries || [];
                }
                if (deniedRes.status === 'fulfilled') {
                    this.monitoring.denied = deniedRes.value.entries || [];
                }
                if (policyRes.status === 'fulfilled') {
                    this.monitoring.policy = policyRes.value;
                }
            } catch (e) {
                console.error('모니터링 데이터 로드 실패:', e);
            }
        },
    };
}
