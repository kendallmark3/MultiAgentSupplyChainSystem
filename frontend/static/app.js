/**
 * Cinematic Demo App State Management
 * Alpine.js state machine for the 4-act autonomous supply chain demo
 */

function appState() {
    return {
        ws: null,
        wsConnected: false,
        step: 0,
        isProcessing: false,
        uploadedImage: null,
        uploadedFile: null,
        isDragging: false,
        sampleImages: [],
        visionResult: null,
        boundingBoxes: [],
        supplierResult: null,
        orderResult: null,
        logisticsResult: null,
        mcpResult: null,
        pendingOrder: null,
        reorderResult: null,
        demoMode: true,
        demoWaiting: false,
        demoQueue: [],
        pendingSupplierResult: null,
        pendingDiscovery: null,
        pendingMemoryStart: false,
        currentThought: '',
        thoughtInterval: null,
        progressPercent: 0,
        progressMessage: '',
        currentSubstep: '',
        substeps: [],
        codeGenerating: false,
        codeExecuting: false,
        generatedCode: '',
        executionOutput: '',
        liveLogStream: [],
        showAgentDiscovery: false,
        discoveredAgent: null,
        discoveryAgentType: null,
        showCode: false,
        showOutput: false,
        visionThoughts: [
            "Initializing Gemini 3 Flash vision pipeline...",
            "Loading OpenCV contour detection kernels...",
            "Analyzing pixel density across shelf regions...",
            "Detecting object boundaries with edge detection...",
            "Classifying detected contours as inventory items...",
            "Cross-referencing item dimensions with known SKUs...",
            "Running statistical validation on count estimates...",
            "Finalizing inventory count with confidence scoring..."
        ],
        memoryThoughts: [
            "Generating embedding vector from visual analysis...",
            "Connecting to AlloyDB via private service connect...",
            "Executing ScaNN approximate nearest neighbor search...",
            "Scanning 1M+ inventory vectors in <50ms...",
            "Ranking supplier matches by cosine similarity...",
            "Retrieving top supplier metadata and pricing..."
        ],
        thoughtIndex: 0,
        audioEnabled: true,
        audioCtx: null,
        humOscillator: null,
        humGain: null,
        orchestratorText: "System Ready",
        showLogs: false,
        rawLogs: [],

        async init() {
            this.connectWebSocket();
            await this.loadSampleImages();
            this.initAudio();
            this.setupAudioCleanup();
        },

        initAudio() {
            try {
                this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            } catch (e) {
                console.warn('Web Audio API not supported:', e);
                this.audioEnabled = false;
            }
        },

        setupAudioCleanup() {
            const cleanup = () => {
                this.stopHum();
                if (this.audioCtx) {
                    try {
                        if (this.humOscillator) { this.humOscillator.stop(); this.humOscillator.disconnect(); this.humOscillator = null; }
                        if (this.humGain) { this.humGain.disconnect(); this.humGain = null; }
                        this.audioCtx.close();
                        this.audioCtx = null;
                    } catch (e) { console.warn('Audio cleanup error:', e); }
                }
            };
            window.addEventListener('beforeunload', cleanup);
            window.addEventListener('unload', cleanup);
            window.addEventListener('pagehide', cleanup);
            document.addEventListener('visibilitychange', () => { if (document.hidden) { cleanup(); } });
        },

        toggleAudio() {
            this.audioEnabled = !this.audioEnabled;
            if (!this.audioEnabled) {
                this.stopHum();
                if (this.audioCtx && this.audioCtx.state === 'running') { this.audioCtx.suspend(); }
            } else {
                if (this.audioCtx && this.audioCtx.state === 'suspended') { this.audioCtx.resume(); }
            }
        },

        playHum() {
            if (!this.audioEnabled || !this.audioCtx) return;
            try {
                this.humOscillator = this.audioCtx.createOscillator();
                this.humGain = this.audioCtx.createGain();
                this.humOscillator.type = 'sine';
                this.humOscillator.frequency.setValueAtTime(100, this.audioCtx.currentTime);
                this.humGain.gain.setValueAtTime(0, this.audioCtx.currentTime);
                this.humGain.gain.linearRampToValueAtTime(0.1, this.audioCtx.currentTime + 0.5);
                this.humOscillator.connect(this.humGain);
                this.humGain.connect(this.audioCtx.destination);
                this.humOscillator.start();
            } catch (e) { console.warn('Failed to play hum:', e); }
        },

        stopHum() {
            if (this.humOscillator && this.humGain) {
                try {
                    this.humGain.gain.linearRampToValueAtTime(0, this.audioCtx.currentTime + 0.3);
                    setTimeout(() => {
                        if (this.humOscillator) { this.humOscillator.stop(); this.humOscillator.disconnect(); this.humOscillator = null; }
                        if (this.humGain) { this.humGain.disconnect(); this.humGain = null; }
                    }, 350);
                } catch (e) {
                    if (this.humOscillator) { try { this.humOscillator.stop(); } catch {} try { this.humOscillator.disconnect(); } catch {} this.humOscillator = null; }
                    if (this.humGain) { try { this.humGain.disconnect(); } catch {} this.humGain = null; }
                }
            }
        },

        playPing() {
            if (!this.audioEnabled || !this.audioCtx) return;
            try {
                const oscillator = this.audioCtx.createOscillator();
                const gainNode = this.audioCtx.createGain();
                oscillator.type = 'sine';
                oscillator.frequency.setValueAtTime(880, this.audioCtx.currentTime);
                gainNode.gain.setValueAtTime(0.3, this.audioCtx.currentTime);
                gainNode.gain.exponentialRampToValueAtTime(0.01, this.audioCtx.currentTime + 0.3);
                oscillator.connect(gainNode);
                gainNode.connect(this.audioCtx.destination);
                oscillator.start();
                oscillator.stop(this.audioCtx.currentTime + 0.3);
            } catch (e) { console.warn('Failed to play ping:', e); }
        },

        playSuccess() {
            if (!this.audioEnabled || !this.audioCtx) return;
            try {
                const playTone = (freq, delay) => {
                    const oscillator = this.audioCtx.createOscillator();
                    const gainNode = this.audioCtx.createGain();
                    oscillator.type = 'sine';
                    oscillator.frequency.setValueAtTime(freq, this.audioCtx.currentTime + delay);
                    gainNode.gain.setValueAtTime(0.2, this.audioCtx.currentTime + delay);
                    gainNode.gain.exponentialRampToValueAtTime(0.01, this.audioCtx.currentTime + delay + 0.15);
                    oscillator.connect(gainNode);
                    gainNode.connect(this.audioCtx.destination);
                    oscillator.start(this.audioCtx.currentTime + delay);
                    oscillator.stop(this.audioCtx.currentTime + delay + 0.15);
                };
                playTone(523.25, 0);
                playTone(659.25, 0.15);
            } catch (e) { console.warn('Failed to play success:', e); }
        },

        startFakeThoughts(type) {
            const thoughts = type === 'vision' ? this.visionThoughts : this.memoryThoughts;
            this.thoughtIndex = 0;
            this.currentThought = thoughts[0];
            const scheduleNext = () => {
                const delay = 1500 + Math.random() * 2000;
                this.thoughtInterval = setTimeout(() => {
                    this.thoughtIndex = (this.thoughtIndex + 1) % thoughts.length;
                    this.currentThought = thoughts[this.thoughtIndex];
                    scheduleNext();
                }, delay);
            };
            scheduleNext();
        },

        stopFakeThoughts() {
            if (this.thoughtInterval) { clearTimeout(this.thoughtInterval); this.thoughtInterval = null; }
            this.currentThought = '';
        },

        simulateProgress() {
            this.progressPercent = 0;
            this.currentSubstep = 'Initializing Gemini 3 Flash...';
            const progressInterval = setInterval(() => {
                if (this.progressPercent < 90) {
                    this.progressPercent += 2;
                    if (this.progressPercent === 10) this.currentSubstep = 'Analyzing image composition...';
                    if (this.progressPercent === 24) this.currentSubstep = 'Generating detection code...';
                    if (this.progressPercent === 40) this.currentSubstep = 'Executing object detection...';
                    if (this.progressPercent === 60) this.currentSubstep = 'Mapping bounding boxes...';
                    if (this.progressPercent === 78) this.currentSubstep = 'Verifying count...';
                } else { clearInterval(progressInterval); }
            }, 500);
        },

        connectToAgent() { this.showAgentDiscovery = false; },

        showModal(agentType, agentData) {
            this.showAgentDiscovery = true;
            this.discoveryAgentType = agentType;
            this.discoveredAgent = agentData;
            if (!this.demoMode) { setTimeout(() => { this.showAgentDiscovery = false; }, 2500); }
        },

        demoPause(action) {
            if (this.demoMode) { this.demoQueue.push(action); this.demoWaiting = true; }
            else { action(); }
        },

        demoContinue() {
            if (this.demoQueue.length > 0) {
                const action = this.demoQueue.shift();
                action();
                this.demoWaiting = this.demoQueue.length > 0;
            }
        },

        toggleDemoMode() { this.demoMode = !this.demoMode; },

        proceedToOrder() {
            this.step = 3;
            this.orchestratorText = "Supplier Agent → Order System (Placing Order)";
            if (this.pendingOrder) { this.applyOrder(); }
        },

        applyOrder() {
            if (!this.pendingOrder) return;
            this.playSuccess();
            this.orderResult = this.pendingOrder;
            this.pendingOrder = null;
            this.orchestratorText = "Order Placed Successfully";
            this.isProcessing = false;
            this.step = 4;
        },

        async loadSampleImages() {
            try {
                const response = await fetch('/api/test-images');
                if (response.ok) { const data = await response.json(); this.sampleImages = data.images || []; }
            } catch (error) { console.error('Failed to load sample images:', error); }
        },

        async selectSampleImage(name) {
            try {
                const response = await fetch(`/api/test-image/${name}`);
                if (response.ok) {
                    const blob = await response.blob();
                    this.uploadedFile = new File([blob], name, { type: blob.type });
                    this.uploadedImage = URL.createObjectURL(blob);
                    this.$nextTick(() => { setTimeout(() => this.startAnalysis(), 500); });
                }
            } catch (error) { console.error('Failed to load sample image:', error); alert('Failed to load sample image. Please try again.'); }
        },

        connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => { console.log('WebSocket connected'); this.wsConnected = true; };
            this.ws.onclose = () => {
                console.log('WebSocket disconnected'); this.wsConnected = false;
                setTimeout(() => { if (!this.wsConnected) { this.connectWebSocket(); } }, 3000);
            };
            this.ws.onerror = (error) => { console.error('WebSocket error:', error); };
            this.ws.onmessage = (event) => { const data = JSON.parse(event.data); this.handleWebSocketMessage(data); };
            setInterval(() => { if (this.ws && this.ws.readyState === WebSocket.OPEN) { this.ws.send('ping'); } }, 30000);
        },

        handleWebSocketMessage(data) {
            console.log('Received:', data);
            this.rawLogs.push({...data, timestamp: new Date().toISOString()});
            if (this.rawLogs.length > 100) { this.rawLogs.shift(); }

            switch(data.type) {
                case 'upload_complete':
                    this.step = 1;
                    this.startFakeThoughts('vision');
                    this.simulateProgress();
                    this.orchestratorText = "Control Tower → Vision Agent (A2A Discovery)";
                    break;

                case 'discovery_start':
                    if (data.agent === 'vision') {
                        this.orchestratorText = "Discovering Vision Agent via A2A...";
                        this.showAgentDiscovery = true;
                        this.discoveredAgent = null;
                        this.discoveryAgentType = 'vision';
                        if (!this.demoMode) { setTimeout(() => { this.showAgentDiscovery = false; }, 2500); }
                    } else if (data.agent === 'supplier') {
                        if (this.step < 2) { this.pendingDiscovery = this.pendingDiscovery || {}; this.pendingDiscovery.started = true; }
                        else { this.orchestratorText = "Discovering Supplier Agent via A2A..."; this.showAgentDiscovery = true; this.discoveredAgent = null; this.discoveryAgentType = 'supplier'; }
                    }
                    break;

                case 'discovery_complete':
                    if (data.agent === 'vision') {
                        this.orchestratorText = "Vision Agent → Gemini 3 Flash (Analyzing)";
                        this.discoveredAgent = { name: data.agent, displayName: data.agent_name || 'Vision Agent', description: data.agent_description || '', endpoint: data.agent_url || '', version: data.agent_version || '1.0.0', skills: data.agent_skills || [], inputModes: data.agent_input_modes || [], outputModes: data.agent_output_modes || [], protocolVersion: data.agent_protocol_version || '', transport: data.agent_transport || '', streaming: data.agent_streaming ?? false };
                    } else if (data.agent === 'supplier') {
                        if (this.step < 2) { this.pendingDiscovery = this.pendingDiscovery || {}; this.pendingDiscovery.agentData = data; }
                        else {
                            this.discoveredAgent = { name: data.agent, displayName: data.agent_name || 'Supplier Agent', description: data.agent_description || '', endpoint: data.agent_url || '', version: data.agent_version || '1.0.0', skills: data.agent_skills || [], inputModes: data.agent_input_modes || [], outputModes: data.agent_output_modes || [], protocolVersion: data.agent_protocol_version || '', transport: data.agent_transport || '', streaming: data.agent_streaming ?? false };
                            this.playPing();
                        }
                    }
                    break;

                case 'vision_start':
                    this.orchestratorText = "Vision Agent → Gemini 3 Flash (Analyzing)";
                    this.playHum();
                    break;

                case 'vision_progress':
                    this.liveLogStream.push({ time: new Date().toLocaleTimeString(), message: data.message, type: data.substep });
                    if (data.substep === 'code_generating' || data.substep === 'code') { this.codeGenerating = true; this.codeExecuting = false; if (this.progressPercent < 30) this.progressPercent = 30; this.currentSubstep = data.message; }
                    else if (data.substep === 'code_executing' || data.substep === 'execution') { this.codeGenerating = false; this.codeExecuting = true; if (this.progressPercent < 50) this.progressPercent = 50; this.currentSubstep = data.message; }
                    else if (data.substep === 'thinking') { this.currentSubstep = data.message; }
                    if (data.code) { this.generatedCode = data.code; }
                    if (data.output) { this.executionOutput += data.output + '\n'; }
                    break;

                case 'vision_complete':
                    this.stopFakeThoughts();
                    this.stopHum();
                    this.progressPercent = 100;
                    this.codeGenerating = false;
                    this.codeExecuting = false;
                    this.currentSubstep = 'Analysis complete';
                    this.visionResult = { item_count: data.item_count, item_type: data.item_type, summary: data.summary, confidence: data.confidence, search_query: data.search_query, hasCodeExecution: (data.result && (data.result.includes("Code output:") || data.result.includes("Total boxes detected:") || data.result.includes("code_execution_result"))) };
                    this.boundingBoxes = data.bounding_boxes || [];
                    this.orchestratorText = "Vision Complete";
                    document.body.classList.add('has-results');
                    if (!this.demoMode) { setTimeout(() => { this.step = 2; this.startFakeThoughts('memory'); this.orchestratorText = "Vision Agent → Supplier Agent (A2A Discovery)"; }, 2000); }
                    this.demoPause(() => {
                        this.step = 2;
                        this.startFakeThoughts('memory');
                        this.orchestratorText = "Vision Agent → Supplier Agent (A2A Discovery)";
                        if (this.pendingDiscovery) {
                            const pd = this.pendingDiscovery;
                            this.pendingDiscovery = null;
                            this.orchestratorText = "Discovering Supplier Agent via A2A...";
                            this.showAgentDiscovery = true;
                            this.discoveryAgentType = 'supplier';
                            if (pd.agentData) {
                                const d = pd.agentData;
                                this.discoveredAgent = { name: d.agent, displayName: d.agent_name || 'Supplier Agent', description: d.agent_description || '', endpoint: d.agent_url || '', version: d.agent_version || '1.0.0', skills: d.agent_skills || [], inputModes: d.agent_input_modes || [], outputModes: d.agent_output_modes || [], protocolVersion: d.agent_protocol_version || '', transport: d.agent_transport || '', streaming: d.agent_streaming ?? false };
                                this.playPing();
                            }
                        }
                        if (this.pendingMemoryStart) { this.pendingMemoryStart = false; this.orchestratorText = "Supplier Agent → AlloyDB ScaNN (Searching)"; }
                    });
                    break;

                case 'vision_error':
                    this.stopFakeThoughts();
                    this.stopHum();
                    this.orchestratorText = "Vision Agent Error";
                    this.isProcessing = false;
                    alert(`Vision Agent Error: ${data.message}`);
                    break;

                case 'memory_start':
                    if (this.step >= 2) { this.orchestratorText = "Supplier Agent → AlloyDB ScaNN (Searching)"; }
                    else { this.pendingMemoryStart = true; }
                    break;

                case 'memory_complete':
                    if (this.step >= 2) { this.stopFakeThoughts(); this.playPing(); }
                    this.pendingSupplierResult = { part: data.part, supplier: data.supplier, confidence: data.confidence };
                    if (this.step >= 2) { this.orchestratorText = "Supplier Match Found"; }
                    this.demoPause(() => {
                        this.stopFakeThoughts();
                        this.supplierResult = this.pendingSupplierResult;
                        this.pendingSupplierResult = null;
                        this.orchestratorText = "Supplier Match Found — Review & Proceed";
                    });
                    break;

                case 'memory_error':
                    this.stopFakeThoughts();
                    this.orchestratorText = "Supplier Agent Error";
                    this.isProcessing = false;
                    alert(`Supplier Agent Error: ${data.message}`);
                    break;

                case 'reorder_assessment':
                    this.reorderResult = {
                        status: data.status,
                        days_until_stockout: data.days_until_stockout,
                        reorder_point: data.reorder_point,
                        recommended_qty: data.recommended_qty,
                        predicted_daily_usage: data.predicted_daily_usage,
                        should_order: data.should_order,
                        reason: data.reason,
                        lead_time_days: data.lead_time_days,
                    };
                    this.orchestratorText = `Reorder Agent: ${data.status} — ${data.reason}`;
                    break;

                case 'order_skipped':
                    if (this.reorderResult) { this.reorderResult.should_order = false; }
                    this.orchestratorText = 'Order blocked — stock is healthy';
                    this.isProcessing = false;
                    break;

                case 'order_placed':
                    this.pendingOrder = { orderId: data.order_id };
                    if (this.step >= 3) { this.applyOrder(); }
                    break;

                case 'logistics_complete':
                    this.logisticsResult = { shipping_cost: data.shipping_cost, carrier: data.carrier, eta: data.eta, origin: data.origin, destination: data.destination };
                    this.orchestratorText = `Shipping: ${data.shipping_cost} via ${data.carrier}`;
                    break;

                case 'logistics_start':
                    this.orchestratorText = 'Calculating shipping cost and ETA...';
                    break;

                case 'mcp_start':
                    this.orchestratorText = 'Sending confirmation via Gmail, Calendar & Sheets...';
                    break;

                case 'mcp_complete':
                    this.mcpResult = { email_sent: data.email_sent, calendar_created: data.calendar_created, sheet_logged: data.sheet_logged };
                    this.orchestratorText = 'All integrations complete ✓';
                    break;

                case 'execution_summary':
                    this.executionSummary = {
                        session_id:        data.session_id,
                        intent:            data.intent,
                        overall_status:    data.overall_status,
                        total_duration_ms: data.total_duration_ms,
                        stages:            data.stages,
                    };
                    this.orchestratorText = `Pipeline complete — ${data.overall_status} in ${data.total_duration_ms}ms`;
                    break;

                case 'pong':
                    break;

                default:
                    console.log('Unknown message type:', data.type);
            }
        },

        handleFileSelect(event) {
            const file = event.target.files[0];
            if (file && file.type.startsWith('image/')) { this.processFile(file); }
        },

        handleDrop(event) {
            this.isDragging = false;
            const file = event.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) { this.processFile(file); }
        },

        processFile(file) {
            this.uploadedFile = file;
            const reader = new FileReader();
            reader.onload = (e) => { this.uploadedImage = e.target.result; };
            reader.readAsDataURL(file);
        },

        resetUpload() {
            this.stopFakeThoughts();
            this.stopHum();
            if (this.audioCtx && this.audioCtx.state === 'running') { this.audioCtx.suspend(); }
            this.uploadedImage = null;
            this.uploadedFile = null;
            this.isProcessing = false;
            this.step = 0;
            this.visionResult = null;
            this.boundingBoxes = [];
            this.supplierResult = null;
            this.orderResult = null;
            this.logisticsResult = null;
            this.mcpResult = null;
            this.pendingOrder = null;
            this.reorderResult = null;
            this.executionSummary = null;
            this.orchestratorText = "System Ready";
            this.rawLogs = [];
            this.progressPercent = 0;
            this.currentSubstep = '';
            this.codeGenerating = false;
            this.codeExecuting = false;
            this.generatedCode = '';
            this.executionOutput = '';
            this.liveLogStream = [];
            this.showAgentDiscovery = false;
            this.discoveredAgent = null;
            this.discoveryAgentType = null;
            this.demoWaiting = false;
            this.demoQueue = [];
            this.pendingSupplierResult = null;
            this.pendingDiscovery = null;
            this.pendingMemoryStart = false;
            document.body.classList.remove('has-results');
        },

        async startAnalysis() {
            if (!this.uploadedFile || this.isProcessing) return;
            this.isProcessing = true;
            this.visionResult = null;
            this.supplierResult = null;
            this.orderResult = null;
            this.reorderResult = null;
            this.executionSummary = null;
            this.rawLogs = [];
            const formData = new FormData();
            formData.append('file', this.uploadedFile);
            try {
                const response = await fetch('/api/analyze', { method: 'POST', body: formData });
                if (!response.ok) { throw new Error('Upload failed'); }
                console.log('Analysis started, listening for WebSocket events...');
            } catch (error) {
                console.error('Upload error:', error);
                alert('Failed to upload image. Please try again.');
                this.isProcessing = false;
                this.step = 0;
            }
        }
    };
}

window.appState = appState;