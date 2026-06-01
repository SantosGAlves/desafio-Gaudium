document.getElementById('form-login').addEventListener('submit', async (e) => {
    e.preventDefault(); // Impede a página de recarregar
    
    const email = document.getElementById('email').value;
    const senha = document.getElementById('senha').value;
    const btn = document.getElementById('btn-submit');
    const errorDiv = document.getElementById('login-error');
    
    // Efeito de carregamento
    btn.textContent = 'Autenticando...';
    btn.disabled = true;
    errorDiv.style.display = 'none';

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, senha })
        });

        const data = await response.json();

        if (response.ok && data.status === 'sucesso') {
            // Login aprovado! Redireciona para o Kanban
            window.location.href = '/';
        } else {
            // Login reprovado (senha errada, etc)
            errorDiv.textContent = data.mensagem || 'Credenciais inválidas.';
            errorDiv.style.display = 'block';
            btn.textContent = 'Entrar na Plataforma';
            btn.disabled = false;
        }
    } catch (err) {
        errorDiv.textContent = 'Erro de conexão com o servidor.';
        errorDiv.style.display = 'block';
        btn.textContent = 'Entrar na Plataforma';
        btn.disabled = false;
    }

    // --- Lógica de Recuperação de Senha ---
document.getElementById('esqueci-senha').addEventListener('click', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('email').value;
    const errorDiv = document.getElementById('login-error');
    
    if (!email) {
        errorDiv.textContent = 'Por favor, preencha o seu E-mail acima e clique em "Esqueceu a senha?".';
        errorDiv.style.background = '#fef2f2';
        errorDiv.style.color = '#ef4444';
        errorDiv.style.borderColor = '#fecaca';
        errorDiv.style.display = 'block';
        return;
    }

    // Feedback visual de carregamento (Azul)
    errorDiv.textContent = 'A processar pedido...';
    errorDiv.style.background = '#eff6ff';
    errorDiv.style.color = '#1e40af';
    errorDiv.style.borderColor = '#bfdbfe';
    errorDiv.style.display = 'block';

    try {
        const response = await fetch('/api/recuperar-senha', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        
        const data = await response.json();
        
        if (data.status === 'sucesso') {
            // Feedback de sucesso (Verde)
            errorDiv.textContent = data.mensagem;
            errorDiv.style.background = '#f0fdf4';
            errorDiv.style.color = '#166534';
            errorDiv.style.borderColor = '#bbf7d0';
        } else {
            // Feedback de erro (Vermelho)
            errorDiv.textContent = 'Erro: ' + data.mensagem;
            errorDiv.style.background = '#fef2f2';
            errorDiv.style.color = '#ef4444';
            errorDiv.style.borderColor = '#fecaca';
        }
    } catch (err) {
        errorDiv.textContent = 'Erro ao contactar o servidor.';
        errorDiv.style.background = '#fef2f2';
        errorDiv.style.color = '#ef4444';
        errorDiv.style.borderColor = '#fecaca';
    }
});
});