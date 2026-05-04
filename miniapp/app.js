const tg = window.Telegram.WebApp;
tg.expand();
tg.ready();

const API_URL = '';

let state = {
    account: null,
    category: null,
    selectedGroups: [],
    photos: [],
    photoPaths: [],
    text: ''
};

let history = [];

function goToPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${pageId}`).classList.add('active');
    history.push(pageId);
    
    if (pageId === 'welcome') tg.BackButton.hide();
    else tg.BackButton.show();
}

function goBack() {
    if (history.length <= 1) return;
    history.pop();
    const prev = history[history.length - 1];
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${prev}`).classList.add('active');
    
    if (prev === 'welcome') tg.BackButton.hide();
}

tg.BackButton.onClick(goBack);

// ===== АККАУНТ =====
function selectAccount(account) {
    state.account = account;
    document.querySelectorAll('#page-account .card').forEach(c => c.classList.remove('selected'));
    event.currentTarget.classList.add('selected');
    setTimeout(() => goToPage('category'), 300);
}

// ===== КАТЕГОРИЯ =====
function selectCategory(category) {
    state.category = category;
    document.querySelectorAll('#page-category .card').forEach(c => c.classList.remove('selected'));
    event.currentTarget.classList.add('selected');
    
    if (category === 'custom') {
        loadGroups();
        setTimeout(() => goToPage('groups'), 300);
    } else {
        setTimeout(() => goToPage('photos'), 300);
    }
}

// ===== ГРУППЫ =====
async function loadGroups() {
    try {
        const res = await fetch('/api/groups', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({initData: tg.initData, account: state.account})
        });
        const data = await res.json();
        
        const container = document.getElementById('groups-list');
        container.innerHTML = '';
        
        data.groups.forEach(g => {
            const div = document.createElement('div');
            div.className = 'group-item';
            div.innerHTML = `
                <div>
                    <div class="group-name">${g.name}</div>
                    <div class="group-id">${g.id}</div>
                </div>
                <div class="group-check">✓</div>
            `;
            div.onclick = () => toggleGroup(g.id, div);
            container.appendChild(div);
        });
    } catch (e) {
        console.error(e);
        tg.showAlert('Ошибка загрузки групп');
    }
}

function toggleGroup(groupId, element) {
    const idx = state.selectedGroups.indexOf(groupId);
    if (idx > -1) {
        state.selectedGroups.splice(idx, 1);
        element.classList.remove('selected');
    } else {
        state.selectedGroups.push(groupId);
        element.classList.add('selected');
    }
    
    const btn = document.getElementById('btn-confirm-groups');
    const count = document.getElementById('selected-count');
    count.textContent = `(${state.selectedGroups.length})`;
    btn.disabled = state.selectedGroups.length === 0;
}

function confirmGroups() {
    goToPage('photos');
}

// ===== ФОТО =====
function handleFiles(files) {
    const newPhotos = Array.from(files);
    state.photos = [...state.photos, ...newPhotos];
    renderPhotos();
}

function renderPhotos() {
    const grid = document.getElementById('photos-grid');
    grid.innerHTML = '';
    
    state.photos.forEach((file, idx) => {
        const div = document.createElement('div');
        div.className = 'photo-item';
        const url = URL.createObjectURL(file);
        div.innerHTML = `
            <img src="${url}" alt="">
            <button class="photo-remove" onclick="removePhoto(${idx})">×</button>
        `;
        grid.appendChild(div);
    });
    
    document.getElementById('btn-photos-next').disabled = state.photos.length === 0;
}

function removePhoto(idx) {
    state.photos.splice(idx, 1);
    renderPhotos();
}

// ===== ТЕКСТ =====
function saveText() {
    state.text = document.getElementById('ad-text').value.trim();
    if (!state.text) {
        tg.showAlert('Введите текст объявления');
        return;
    }
    updatePreview();
    goToPage('preview');
}

// ===== ПРЕДПРОСМОТР =====
function updatePreview() {
    const photosContainer = document.getElementById('preview-photos');
    photosContainer.innerHTML = '';
    state.photos.forEach(file => {
        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        photosContainer.appendChild(img);
    });
    
    document.getElementById('preview-text').textContent = state.text;
    
    const accNames = {accessories: 'Аксессуары', autosale: 'Дианы'};
    document.getElementById('preview-account').textContent = accNames[state.account];
    
    const catNames = {usual: 'Обычные группы', large: 'Крупные группы', custom: 'Выборочно'};
    document.getElementById('preview-category').textContent = catNames[state.category];
    
    if (state.category === 'custom') {
        document.getElementById('preview-groups-item').style.display = 'flex';
        document.getElementById('preview-groups').textContent = state.selectedGroups.length + ' групп';
    } else {
        document.getElementById('preview-groups-item').style.display = 'none';
    }
}

function editAccount() { goToPage('account'); }
function editCategory() { goToPage('category'); }
function editPhotos() { goToPage('photos'); }
function editText() { goToPage('text'); }

// ===== ПУБЛИКАЦИЯ =====
async function publish() {
    goToPage('sending');
    
    // Загружаем фото на сервер
    const formData = new FormData();
    formData.append('initData', tg.initData);
    state.photos.forEach((file, i) => formData.append(`photo${i}`, file));
    
    let photoPaths = [];
    try {
        const uploadRes = await fetch('/api/upload-photos', {method: 'POST', body: formData});
        const uploadData = await uploadRes.json();
        photoPaths = uploadData.photos || [];
    } catch (e) {
        console.error('Upload error:', e);
    }
    
    // Отправляем пост
    try {
        const res = await fetch('/api/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                initData: tg.initData,
                account: state.account,
                category: state.category === 'custom' ? 'usual' : state.category,
                text: state.text,
                photos: photoPaths,
                selected_groups: state.category === 'custom' ? state.selectedGroups : null
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showSendingAnimation(data.detailed || []);
            setTimeout(() => showResult(data.report), 2000);
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    } catch (e) {
        tg.showAlert('Ошибка: ' + e.message);
        goToPage('preview');
    }
}

function showSendingAnimation(results) {
    const container = document.getElementById('groups-status');
    container.innerHTML = '';
    
    results.forEach((r, i) => {
        setTimeout(() => {
            const div = document.createElement('div');
            div.className = 'status-item';
            div.innerHTML = `
                <span class="status-group">Группа ${r.group}</span>
                <span class="status-text">
                    <span class="spinner"></span>
                    <span>Отправляется...</span>
                </span>
            `;
            container.appendChild(div);
            
            setTimeout(() => {
                const isSuccess = r.status === 'success';
                div.className = 'status-item ' + (isSuccess ? 'success' : 'error');
                div.innerHTML = `
                    <span class="status-group">Группа ${r.group}</span>
                    <span class="status-text">
                        ${isSuccess ? '✅ Готово' : '❌ Ошибка'}
                    </span>
                `;
            }, 600 + Math.random() * 800);
        }, i * 250);
    });
}

function showResult(report) {
    document.getElementById('result-report').textContent = '📋 Отправка завершена!\n\n' + report;
    goToPage('result');
    tg.HapticFeedback.notificationOccurred('success');
}

function resetApp() {
    state = {
        account: null,
        category: null,
        selectedGroups: [],
        photos: [],
        photoPaths: [],
        text: ''
    };
    document.getElementById('ad-text').value = '';
    document.querySelectorAll('.card, .group-item').forEach(c => c.classList.remove('selected'));
    document.getElementById('photos-grid').innerHTML = '';
    document.getElementById('groups-list').innerHTML = '';
    history = [];
    goToPage('welcome');
}