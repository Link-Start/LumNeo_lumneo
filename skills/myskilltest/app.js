import * as THREE from 'three';

/**
 * LumNeo AI Cinematic Website - 3D Scene
 * 使用 Three.js 构建电影级 3D 场景
 */

class SceneController {
    constructor() {
        this.container = document.getElementById('canvas-container');
        this.scenes = [];
        this.init();
    }

    init() {
        // 1. 场景与相机设置
        this.scene = new THREE.Scene();
        // 添加轻微的背景雾效，增加景深感
        this.scene.fog = new THREE.FogExp2(0x050510, 0.002);

        this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        this.camera.position.z = 30;

        // 2. 渲染器设置
        this.renderer = new THREE.WebGLRenderer({
            antialias: true, // 开启抗锯齿
            alpha: true,     // 允许背景透明
        });
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);

        // 3. 灯光系统 (Cinematic Lighting)
        this.setupLighting();

        // 4. 核心对象：AI 核心 (The Core)
        this.createAICore();

        // 5. 粒子系统 (Background Particles)
        this.createParticles();

        // 6. 事件监听
        this.mouse = new THREE.Vector2();
        this.targetRotation = new THREE.Vector2();
        
        window.addEventListener('resize', this.onResize.bind(this));
        window.addEventListener('mousemove', this.onMouseMove.bind(this));

        // 开始动画循环
        this.animate();
    }

    setupLighting() {
        // 环境光：基础亮度
        const ambientLight = new THREE.AmbientLight(0x404040, 1);
        this.scene.add(ambientLight);

        // 主光源：明亮的青灰色顶光
        const spotLight = new THREE.SpotLight(0xffffff, 2);
        spotLight.position.set(10, 20, 10);
        spotLight.angle = Math.PI / 6;
        spotLight.penumbra = 1;
        this.scene.add(spotLight);

        // 辅光源 1：青色，营造科技感
        const pointLight1 = new THREE.PointLight(0x00f3ff, 2, 50);
        pointLight1.position.set(-10, -5, 5);
        this.scene.add(pointLight1);

        // 辅光源 2：紫色，增加层次感
        const pointLight2 = new THREE.PointLight(0xbc13fe, 2, 50);
        pointLight2.position.set(10, 5, 5);
        this.scene.add(pointLight2);
    }

    createAICore() {
        const coreGroup = new THREE.Group();

        // 1. 核心形状：二十面体 (Icosahedron)
        const geometry = new THREE.IcosahedronGeometry(5, 1);
        
        // 材质：金属感 + 高反射 + 边缘光
        const material = new THREE.MeshStandardMaterial({
            color: 0x111111,
            metalness: 0.9,
            roughness: 0.1,
            flatShading: true, // 低多边形风格
        });

        const coreMesh = new THREE.Mesh(geometry, material);
        coreGroup.add(coreMesh);

        // 2. 线框外壳 (Wireframe Shell) - 模拟计算网络层
        const wireGeo = new THREE.IcosahedronGeometry(6, 2);
        const wireMat = new THREE.MeshBasicMaterial({
            color: 0x00f3ff,
            wireframe: true,
            transparent: true,
            opacity: 0.3
        });
        this.wireShell = new THREE.Mesh(wireGeo, wireMat);
        coreGroup.add(this.wireShell);

        // 3. 外圈粒子环 (Particle Ring)
        const ringGeo = new THREE.BufferGeometry();
        const ringCount = 200;
        const ringPositions = [];
        
        for (let i = 0; i < ringCount; i++) {
            const angle = (i / ringCount) * Math.PI * 2;
            // 增加一点高度随机性，形成扁平的盘状
            const radius = 8 + Math.random() * 1; 
            const x = Math.cos(angle) * radius;
            const y = (Math.random() - 0.5) * 0.5;
            const z = Math.sin(angle) * radius;
            ringPositions.push(x, y, z);
        }
        
        ringGeo.setAttribute('position', new THREE.Float32BufferAttribute(ringPositions, 3));
        const ringMat = new THREE.PointsMaterial({
            color: 0x00f3ff,
            size: 0.15,
            transparent: true,
            opacity: 0.8
        });
        this.ringSystem = new THREE.Points(ringGeo, ringMat);
        coreGroup.add(this.ringSystem);

        this.scene.add(coreGroup);
        this.coreGroup = coreGroup;
    }

    createParticles() {
        // 创建无数漂浮的数据尘埃
        const geometry = new THREE.BufferGeometry();
        const count = 1500;
        const positions = new Float32Array(count * 3);
        const colors = new Float32Array(count * 3);

        for (let i = 0; i < count; i++) {
            const i3 = i * 3;
            // 随机分布在空间中
            positions[i3] = (Math.random() - 0.5) * 100;
            positions[i3 + 1] = (Math.random() - 0.5) * 100;
            positions[i3 + 2] = (Math.random() - 0.5) * 100;

            // 随机颜色（青或白）
            colors[i3] = Math.random() * 0.5;
            colors[i3 + 1] = Math.random() * 0.8 + 0.2;
            colors[i3 + 2] = 1.0; 
        }

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
            size: 0.15,
            vertexColors: true,
            transparent: true,
            opacity: 0.6,
            blending: THREE.AdditiveBlending
        });

        this.particles = new THREE.Points(geometry, material);
        this.scene.add(this.particles);
    }

    onResize() {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
    }

    onMouseMove(event) {
        // 归一化鼠标坐标 [-1, 1]
        this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
    }

    animate() {
        requestAnimationFrame(this.animate.bind(this));

        const time = Date.now() * 0.001;

        // 1. 核心呼吸与自转
        if (this.coreGroup) {
            this.coreGroup.rotation.x += 0.002;
            this.coreGroup.rotation.y += 0.003;
            
            // 模拟呼吸效果：缩放
            const scale = 1 + Math.sin(time * 2) * 0.02;
            this.coreGroup.scale.set(scale, scale, scale);

            if (this.wireShell) {
                // 线框层反向旋转，增加视差感
                this.wireShell.rotation.x -= 0.004;
                this.wireShell.rotation.z += 0.002;
                // 颜色渐变动画
                const hue = (time * 0.1) % 1;
                this.wireShell.material.color.setHSL(hue * 0.2 + 0.5, 1, 0.5); 
            }
        }

        // 2. 粒子环旋转
        if (this.ringSystem) {
            this.ringSystem.rotation.z -= 0.005;
        }

        // 3. 背景粒子缓慢移动
        if (this.particles) {
            this.particles.rotation.y += 0.0005;
            this.particles.rotation.x -= 0.0002;
        }

        // 4. 相机跟随鼠标（视差效果）
        this.targetRotation.x = this.mouse.y * 0.5;
        this.targetRotation.y = this.mouse.x * 0.5;
        
        // 平滑插值移动相机
        this.camera.position.x += (this.mouse.x * 2 - this.camera.position.x) * 0.05;
        this.camera.position.y += (this.mouse.y * 2 - this.camera.position.y) * 0.05;
        this.camera.lookAt(this.scene.position);

        this.renderer.render(this.scene, this.camera);
    }
}

// 初始化
window.onload = () => {
    new SceneController();
};
