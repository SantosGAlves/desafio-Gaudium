document.addEventListener('DOMContentLoaded', () => {
    const modalNovo = document.getElementById('modal-nova-demanda');
    const modalGestao = document.getElementById('modal-gestao-ticket');
    let modoMeusChamados = false;
    let ticketAbertoAtual = null; 
    let cronometroInterval = null; 

    const CustomUI = {
        dialog: document.getElementById('custom-dialog'),
        title: document.getElementById('dialog-title'),
        msg: document.getElementById('dialog-msg'),
        input: document.getElementById('dialog-input'),
        btnConfirm: document.getElementById('dialog-btn-confirm'),
        btnCancel: document.getElementById('dialog-btn-cancel'),
        mostrar(tipo, titulo, mensagem, callback) {
            this.title.textContent = titulo;
            this.msg.textContent = mensagem;
            this.dialog.style.display = 'flex';
            this.input.style.display = tipo === 'prompt' ? 'block' : 'none';
            this.btnCancel.style.display = tipo === 'alert' ? 'none' : 'block';
            this.input.value = '';
            this.btnConfirm.onclick = null;
            this.btnCancel.onclick = null;
            this.btnConfirm.onclick = () => { this.dialog.style.display = 'none'; if(tipo === 'prompt') callback(this.input.value); else callback(true); };
            this.btnCancel.onclick = () => { this.dialog.style.display = 'none'; if(tipo !== 'alert') callback(false); };
        },
        alert(msg) { return new Promise(res => this.mostrar('alert', 'Aviso', msg, res)); },
        confirm(msg) { return new Promise(res => this.mostrar('confirm', 'Confirmação', msg, res)); }
    };

    function formatarData(data) { return data ? new Date(data + 'T00:00:00').toLocaleDateString('pt-BR') : 'Sem prazo'; }
    function formatarTempo(min) { const h = Math.floor(min / 60); const m = Math.floor(min % 60); return `${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m`; }

    function iniciarCronometroVisual(minutosJaGastos, horaInicioISO) {
        clearInterval(cronometroInterval);
        const display = document.getElementById('ticket-tempo-view');
        if (!horaInicioISO) { display.textContent = formatarTempo(minutosJaGastos); return; }
        const dataInicio = new Date(horaInicioISO.replace('Z', '+00:00')).getTime();
        function atualizar() { display.textContent = formatarTempo(minutosJaGastos + Math.floor((new Date().getTime() - dataInicio) / 60000)); }
        atualizar(); cronometroInterval = setInterval(atualizar, 60000);
    }

    function atualizarContadores() {
        ['entrada', 'andamento', 'pausado', 'concluido'].forEach(id => {
            document.getElementById(`count-${id}`).textContent = document.querySelectorAll(`#col-${id} .card`).length;
        });
    }

    async function carregarDemandas() {
        const response = await fetch(modoMeusChamados ? '/api/demandas?meus=true' : '/api/demandas');
        const data = await response.json();
        if (data.status === 'sucesso') {
            document.querySelectorAll('.kanban-cards').forEach(el => el.innerHTML = '');
            window.ticketsData = data.dados; 
            data.dados.forEach(criarCardNaTela);
            atualizarContadores();
        }
    }

    function criarCardNaTela(demanda) {
        let classeTag = demanda.prioridade === 'alta' ? 'tag-alta' : (demanda.prioridade === 'baixa' ? 'tag-baixa' : 'tag-media');
        
        // --- VERIFICAÇÃO DE PERMISSÃO ---
        const userDept = (window.USER_DEPT || '').toUpperCase();
        const ticketDept = (demanda.departamento || '').toUpperCase();
        const isAdmin = ['GERAL', 'ADMIN', 'DIRETORIA'].includes(userDept);
        const podeEditar = isAdmin || userDept === ticketDept;
        const dragStatus = podeEditar ? 'true' : 'false';
        
        let percentualSLA = 0; let slaClass = ''; let dataCriacaoCurta = '--/--/----';
        if (demanda.created_at) {
            const dataObj = new Date(demanda.created_at);
            dataCriacaoCurta = dataObj.toLocaleDateString('pt-BR');
            if (demanda.prazo) {
                const dataCriacao = dataObj.getTime();
                const dataPrazo = new Date(demanda.prazo + 'T23:59:59').getTime();
                const agora = new Date().getTime();
                const tempoTotal = dataPrazo - dataCriacao;
                const tempoDecorrido = agora - dataCriacao;

                if (agora > dataPrazo && demanda.status !== 'concluido') { percentualSLA = 100; slaClass = 'danger'; } 
                else if (demanda.status === 'concluido') { percentualSLA = 100; slaClass = ''; } 
                else if (tempoDecorrido > 0) {
                    percentualSLA = Math.min(100, Math.max(0, (tempoDecorrido / tempoTotal) * 100));
                    if (percentualSLA >= 90) slaClass = 'danger'; else if (percentualSLA >= 75) slaClass = 'warning';
                }
            }
        }

        const cardHTML = `
            <div class="card" draggable="${dragStatus}" style="${podeEditar ? '' : 'cursor: pointer; opacity: 0.9;'}" data-id="${demanda.id}" onclick="abrirGestaoTicket('${demanda.id}')">
                <div class="card-header-top">
                    <h3 class="card-title-inline"><span class="card-codigo-inline">#${demanda.codigo || '0'}</span> ${demanda.titulo}</h3>
                </div>
                <div class="card-tags">
                    <span class="tag ${classeTag}">${demanda.prioridade.toUpperCase()}</span>
                    <span class="tag tag-dept"><i class="ph ph-arrow-right"></i> ${demanda.departamento}</span>
                </div>
                <div class="card-meta">
                    <div class="meta-item"><i class="ph ph-buildings"></i> Setor: ${demanda.setor_solicitante || 'Não informado'}</div>
                    <div class="meta-item"><i class="ph ph-user"></i> De: ${demanda.solicitante || 'Sistema'}</div>
                </div>
                <div class="card-sla-wrapper">
                    <div class="card-sla-bars"><div class="card-sla-progress ${slaClass}" style="width: ${percentualSLA}%;"></div></div>
                    <span class="card-date" title="Data de Criação">${dataCriacaoCurta}</span>
                </div>
            </div>`;
            
        let col = '#col-entrada .kanban-cards';
        if (demanda.status === 'andamento') col = '#col-andamento .kanban-cards';
        if (demanda.status === 'pausado') col = '#col-pausado .kanban-cards';
        if (demanda.status === 'concluido') col = '#col-concluido .kanban-cards';
        document.querySelector(col).insertAdjacentHTML('beforeend', cardHTML);
        aplicarEventosDragAndDrop();
    }

    window.abrirGestaoTicket = (id) => {
        ticketAbertoAtual = window.ticketsData.find(t => t.id === id);
        if(!ticketAbertoAtual) return;

        document.getElementById('ticket-codigo').textContent = `#${ticketAbertoAtual.codigo || '0'}`;
        document.getElementById('ticket-titulo-view').textContent = ticketAbertoAtual.titulo;
        
        const btnPlay = document.getElementById('btn-play-ticket'); const btnPause = document.getElementById('btn-pause-ticket');
        btnPlay.classList.remove('ativo'); btnPause.classList.remove('ativo');
        if(ticketAbertoAtual.status_execucao === 'play') btnPlay.classList.add('ativo');
        if(ticketAbertoAtual.status_execucao === 'pausado') btnPause.classList.add('ativo');

        document.getElementById('ticket-descricao-view').textContent = ticketAbertoAtual.descricao;
        document.getElementById('ticket-solicitante-view').textContent = ticketAbertoAtual.solicitante;
        document.getElementById('ticket-setor-origem').textContent = `Setor: ${ticketAbertoAtual.setor_solicitante || '-'}`;
        document.getElementById('ticket-dept-view').textContent = ticketAbertoAtual.departamento;
        document.getElementById('ticket-resp-view').textContent = ticketAbertoAtual.responsavel || 'Aguardando Atribuição';
        document.getElementById('ticket-prazo-view').textContent = formatarData(ticketAbertoAtual.prazo);
        
        const mapStatus = { andamento: 'Em Atendimento', pausado: 'Pausado', concluido: 'Finalizado' };
        document.getElementById('ticket-status-view').textContent = mapStatus[ticketAbertoAtual.status] || 'A Fazer';

        if (ticketAbertoAtual.status_execucao === 'play') iniciarCronometroVisual(ticketAbertoAtual.tempo_gasto, ticketAbertoAtual.hora_inicio);
        else iniciarCronometroVisual(ticketAbertoAtual.tempo_gasto, null); 

        const containerHist = document.getElementById('ticket-historico-view');
        containerHist.innerHTML = ''; 
        if (ticketAbertoAtual.historico) {
            ticketAbertoAtual.historico.split('\n').filter(l => l.trim() !== '').forEach(linha => {
                const partes = linha.replace('• ', '').split(': ');
                containerHist.insertAdjacentHTML('beforeend', `<div class="timeline-item"><span class="tl-autor">${partes[0] || 'Sistema'}</span><span class="tl-texto">${partes.slice(1).join(': ') || linha}</span></div>`);
            });
        } else containerHist.innerHTML = '<p style="color:#94a3b8; font-size:0.9rem;">Nenhuma atualização registrada.</p>';
        
        const barraSLA = document.getElementById('ticket-sla-bar'); const textSLA = document.getElementById('ticket-sla-texto'); const pctSLA = document.getElementById('ticket-sla-porcentagem');
        barraSLA.className = 'sla-progress-bar'; 
        
        if (ticketAbertoAtual.prazo && ticketAbertoAtual.created_at) {
            const dataCriacao = new Date(ticketAbertoAtual.created_at).getTime();
            const dataPrazo = new Date(ticketAbertoAtual.prazo + 'T23:59:59').getTime();
            const agora = new Date().getTime();
            const tempoTotalSLA = dataPrazo - dataCriacao; const tempoDecorrido = agora - dataCriacao;
            let porcentagem = 0;

            if (agora > dataPrazo && ticketAbertoAtual.status !== 'concluido') {
                porcentagem = 100; textSLA.textContent = "Atrasado"; textSLA.style.color = "#ef4444"; barraSLA.classList.add('danger');
            } else if (ticketAbertoAtual.status === 'concluido') {
                porcentagem = 100; textSLA.textContent = "SLA Cumprido"; textSLA.style.color = "var(--col-doing)"; barraSLA.style.backgroundColor = "var(--col-doing)";
            } else if (tempoDecorrido > 0) {
                porcentagem = Math.min(100, Math.max(0, (tempoDecorrido / tempoTotalSLA) * 100));
                if (porcentagem >= 90) { textSLA.textContent = "Risco Crítico"; textSLA.style.color = "#ef4444"; barraSLA.classList.add('danger'); } 
                else if (porcentagem >= 75) { textSLA.textContent = "Atenção"; textSLA.style.color = "#f59e0b"; barraSLA.classList.add('warning'); } 
                else { textSLA.textContent = "Dentro do Prazo"; textSLA.style.color = "var(--text-muted)"; }
            }
            barraSLA.style.width = `${porcentagem}%`; pctSLA.textContent = `${Math.round(porcentagem)}%`;
        } else { barraSLA.style.width = `0%`; textSLA.textContent = "SLA Indefinido"; pctSLA.textContent = "--"; }
        
        // --- VERIFICAÇÃO MODO READ-ONLY ---
        const userDept = (window.USER_DEPT || '').toUpperCase();
        const ticketDept = (ticketAbertoAtual.departamento || '').toUpperCase();
        const isAdmin = ['GERAL', 'ADMIN', 'DIRETORIA'].includes(userDept);
        const podeEditar = isAdmin || userDept === ticketDept;

        const botoesAcao = ['btn-play-ticket', 'btn-pause-ticket', 'btn-finish-ticket', 'btn-delete-ticket'];
        botoesAcao.forEach(idBtn => {
            const btn = document.getElementById(idBtn);
            if(btn) btn.style.display = podeEditar ? 'flex' : 'none';
        });

        modalGestao.style.display = 'flex'; 
    };

    document.getElementById('close-gestao').addEventListener('click', () => { clearInterval(cronometroInterval); modalGestao.style.display = 'none'; });

    async function dispararAcaoAPI(payload, fecharModal = false) {
        if(!ticketAbertoAtual) return;
        const response = await fetch(`/api/demandas/${ticketAbertoAtual.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        
        const data = await response.json();
        
        if (response.ok && data.status === 'sucesso') {
            if (fecharModal) { clearInterval(cronometroInterval); modalGestao.style.display = 'none'; } 
            else { window.ticketsData = window.ticketsData.map(t => t.id === ticketAbertoAtual.id ? data.dados[0] : t); abrirGestaoTicket(ticketAbertoAtual.id); }
            carregarDemandas(); 
        } else {
            CustomUI.alert(data.mensagem || "Erro na operação.");
        }
    }

    document.getElementById('btn-play-ticket').addEventListener('click', () => dispararAcaoAPI({ status_execucao: 'play' }));
    document.getElementById('btn-pause-ticket').addEventListener('click', () => dispararAcaoAPI({ status_execucao: 'pausado' }));
    document.getElementById('btn-finish-ticket').addEventListener('click', async () => { if(await CustomUI.confirm("Finalizar este chamado?")) dispararAcaoAPI({ status: 'concluido' }, true); });
    document.getElementById('btn-delete-ticket').addEventListener('click', async () => {
        if(await CustomUI.confirm("A exclusão é permanente. Continuar?")) {
            await fetch(`/api/demandas/${ticketAbertoAtual.id}`, { method: 'DELETE' });
            clearInterval(cronometroInterval); modalGestao.style.display = 'none'; carregarDemandas();
        }
    });
    document.getElementById('btn-add-historico').addEventListener('click', () => {
        const txtBox = document.getElementById('novo-comentario');
        if (txtBox.value.trim() !== "") { dispararAcaoAPI({ novo_historico: txtBox.value }); txtBox.value = ''; } else CustomUI.alert("A nota não pode estar vazia.");
    });

    document.getElementById('btn-nova-demanda').addEventListener('click', () => modalNovo.style.display = 'flex');
    document.getElementById('close-novo-demanda').addEventListener('click', () => modalNovo.style.display = 'none');
    
    document.getElementById('form-demanda').addEventListener('submit', async (e) => {
        e.preventDefault(); 
        const payload = {
            setor_solicitante: document.getElementById('setor_solicitante').value, 
            titulo: document.getElementById('titulo').value,
            descricao: document.getElementById('descricao').value, 
            departamento: document.getElementById('departamento').value,
            prioridade: document.getElementById('prioridade').value, 
            prazo: document.getElementById('prazo').value
        };
        const response = await fetch('/api/demandas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if(response.ok) { document.getElementById('form-demanda').reset(); modalNovo.style.display = 'none'; carregarDemandas(); }
    });

    document.querySelector('.search-bar input').addEventListener('input', (e) => {
        const termo = e.target.value.toLowerCase();
        document.querySelectorAll('.card').forEach(card => card.style.display = card.innerText.toLowerCase().includes(termo) ? 'block' : 'none');
    });

    const [btnKanban, btnMeusChamados] = document.querySelectorAll('.menu-item:not(#btn-gestao-usuarios)'); // Ignora o botão de gestão no toggle do menu
    btnMeusChamados.addEventListener('click', (e) => { e.preventDefault(); btnKanban.classList.remove('active'); btnMeusChamados.classList.add('active'); modoMeusChamados = true; carregarDemandas(); });
    btnKanban.addEventListener('click', (e) => { e.preventDefault(); btnMeusChamados.classList.remove('active'); btnKanban.classList.add('active'); modoMeusChamados = false; carregarDemandas(); });
    document.getElementById('btn-logout')?.addEventListener('click', async (e) => { e.preventDefault(); await fetch('/api/logout', { method: 'POST' }); window.location.href = '/login'; });

    function aplicarEventosDragAndDrop() {
        document.querySelectorAll('.card').forEach(card => {
            if(card.dataset.dragAtivo || card.getAttribute('draggable') === 'false') return; 
            card.dataset.dragAtivo = true;
            card.addEventListener('dragstart', () => card.classList.add('dragging'));
            card.addEventListener('dragend', () => card.classList.remove('dragging'));
        });
        document.querySelectorAll('.kanban-column').forEach(coluna => {
            const containerCards = coluna.querySelector('.kanban-cards');
            if(coluna.dataset.dropAtivo) return; coluna.dataset.dropAtivo = true;
            coluna.addEventListener('dragover', e => { e.preventDefault(); containerCards.classList.add('drag-over'); const dragCard = document.querySelector('.dragging'); if (dragCard) containerCards.appendChild(dragCard); });
            coluna.addEventListener('dragleave', () => containerCards.classList.remove('drag-over'));
            coluna.addEventListener('drop', async () => {
                containerCards.classList.remove('drag-over');
                const dragCard = document.querySelector('.dragging');
                if(dragCard) {
                    const cardId = dragCard.getAttribute('data-id');
                    let novoStatus = coluna.id.replace('col-', '');
                    if(novoStatus === 'entrada') novoStatus = 'entrada';
                    
                    const response = await fetch(`/api/demandas/${cardId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: novoStatus }) });
                    const data = await response.json();
                    if (!response.ok || data.status === 'erro') {
                        CustomUI.alert(data.mensagem || "Você não tem permissão para mover este chamado.");
                    }
                    carregarDemandas();
                }
            });
        });
    }

    // ==========================================
    // LÓGICA DE GESTÃO DE USUÁRIOS (COM TRAVAS DE SEGURANÇA)
    // ==========================================
    const modalUsuarios = document.getElementById('modal-gestao-usuarios');
    const btnGestaoUsuarios = document.getElementById('btn-gestao-usuarios');
    const closeUsuariosBtn = document.getElementById('close-usuarios');
    const formCadastroUser = document.getElementById('form-cadastro-user');

    if (btnGestaoUsuarios) {
        btnGestaoUsuarios.addEventListener('click', (e) => {
            e.preventDefault();
            modalUsuarios.style.display = 'flex';
            carregarTabelaUsuarios();
        });
    }

    if (closeUsuariosBtn) {
        closeUsuariosBtn.addEventListener('click', () => modalUsuarios.style.display = 'none');
    }

    async function carregarTabelaUsuarios() {
        const res = await fetch('/api/admin/usuarios');
        const data = await res.json();
        const tbody = document.getElementById('user-table-body');
        if (tbody && data.dados) {
            tbody.innerHTML = data.dados.map(u => `
                <tr style="border-top: 1px solid #e2e8f0;">
                    <td style="padding: 12px 15px;">${u.nome}</td>
                    <td style="padding: 12px 15px;">${u.email}</td>
                    <td style="padding: 12px 15px;"><span class="tag tag-dept">${u.departamento}</span></td>
                    <td style="padding: 12px 15px; text-align: center;">
                        <button onclick="excluirUser('${u.email}')" style="border:none; background:none; color:#ef4444; cursor:pointer; font-size: 1.2rem; transition: 0.2s;"><i class="ph ph-trash"></i></button>
                    </td>
                </tr>
            `).join('');
        }
    }

    if (formCadastroUser) {
        formCadastroUser.addEventListener('submit', async (e) => {
            e.preventDefault();
            const payload = {
                nome: document.getElementById('novo-nome').value,
                email: document.getElementById('novo-email').value,
                departamento: document.getElementById('novo-dept').value
            };
            const response = await fetch('/api/admin/usuarios', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
            
            if (response.ok) {
                formCadastroUser.reset();
                carregarTabelaUsuarios();
                CustomUI.alert("Usuário cadastrado com sucesso!");
            } else {
                CustomUI.alert("Erro ao cadastrar o usuário. Verifique as permissões.");
            }
        });
    }

    window.excluirUser = async (email) => {
        if (await CustomUI.confirm(`Tem certeza que deseja excluir o acesso de ${email}?`)) {
            await fetch(`/api/admin/usuarios/${email}`, { method: 'DELETE' });
            carregarTabelaUsuarios();
        }
    };
    
    // Inicia carregamento da tela
    carregarDemandas();
});