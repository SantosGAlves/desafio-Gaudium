from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import threading
import httpx
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime, timezone

load_dotenv()

app = Flask(__name__)
app.secret_key = 'gaudium_super_secreta_2026' 

url: str = os.environ.get("SUPABASE_URL") or ""
key: str = os.environ.get("SUPABASE_KEY") or ""
n8n_url: str = os.environ.get("N8N_WEBHOOK_URL") or ""
supabase: Client = create_client(url, key) if url and key else None

def disparar_n8n(evento, ticket_data):
    if not n8n_url: return
    def enviar():
        try:
            httpx.post(n8n_url, json={"evento": evento, "timestamp": datetime.now(timezone.utc).isoformat(), "ticket": ticket_data}, timeout=5.0)
        except Exception as e:
            print(f"Erro ao comunicar com n8n: {e}")
    threading.Thread(target=enviar).start()

@app.route('/')
def index():
    if 'usuario_id' not in session: return redirect(url_for('login_page'))
    return render_template('index.html', usuario_logado=session.get('usuario_nome'), usuario_dept=session.get('usuario_dept'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def fazer_login():
    try:
        dados = request.json
        auth_response = supabase.auth.sign_in_with_password({"email": dados.get('email'), "password": dados.get('senha')})
        
        perfil_response = supabase.table('usuarios').select('*').eq('email', dados.get('email')).execute()
        nome = dados.get('email').split('@')[0]
        dept = 'Geral'

        if len(perfil_response.data) > 0:
            nome = perfil_response.data[0]['nome']
            dept = perfil_response.data[0]['departamento']

        session['usuario_id'] = auth_response.user.id
        session['usuario_nome'] = nome
        session['usuario_dept'] = dept
        session['usuario_email'] = dados.get('email') # <--- NOVA LINHA: Guarda o e-mail na sessão
        
        return jsonify({"status": "sucesso", "mensagem": "Bem-vindo!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": "E-mail ou senha incorretos."}), 401
    
@app.route('/api/recuperar-senha', methods=['POST'])
def recuperar_senha():
    try:
        dados = request.json
        email = dados.get('email')
        
        if not email:
            return jsonify({"status": "erro", "mensagem": "E-mail não fornecido."}), 400
            
        # Função NATIVA e segura do Supabase para reset de senha
        supabase.auth.reset_password_email(email)
        
        # Retornamos sucesso genérico por segurança (para não confirmar a hackers se o e-mail existe ou não na base)
        return jsonify({"status": "sucesso", "mensagem": "Se o e-mail existir na nossa base, receberá um link em instantes."})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/nova-senha')
def nova_senha_page():
    # Renderiza a tela para o usuário digitar a nova senha
    return render_template('nova-senha.html')

@app.route('/api/atualizar-senha', methods=['POST'])
def atualizar_senha():
    try:
        dados = request.json
        token = dados.get('access_token')
        nova_senha = dados.get('senha')
        
        if not token:
            return jsonify({"status": "erro", "mensagem": "Link inválido ou expirado."}), 400

        # Autentica temporariamente o usuário usando o token que veio no link do e-mail
        supabase.auth.set_session(token, "")
        
        # Atualiza a senha no Supabase
        supabase.auth.update_user({"password": nova_senha})
        
        # Limpa a sessão para obrigar o usuário a fazer o login normal com a nova senha
        supabase.auth.sign_out()
        
        return jsonify({"status": "sucesso"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def fazer_logout():
    session.clear() 
    return jsonify({"status": "sucesso"})

@app.route('/api/demandas', methods=['GET'])
def get_demandas():
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    try:
        response = supabase.table('demandas').select("*").order('created_at', desc=True).execute()
        dados = response.data
        
        usuario_dept = session.get('usuario_dept')
        nome_usuario = session.get('usuario_nome')
        is_admin = usuario_dept and usuario_dept.upper() in ['GERAL', 'ADMIN', 'DIRETORIA']

        if request.args.get('meus') == 'true':
            # Aba Meus Chamados: O usuário vê APENAS o que ele solicitou.
            dados = [d for d in dados if d.get('solicitante') == nome_usuario]
        else:
            # Aba Kanban: O usuário vê APENAS os chamados onde a sua área é o DESTINO (A fila de trabalho dele)
            if not is_admin:
                dados = [d for d in dados if d.get('departamento') == usuario_dept]
            
        return jsonify({"status": "sucesso", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/demandas', methods=['POST'])
def criar_demanda():
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    try:
        dados = request.json
        nova_demanda = {
            "setor_solicitante": session.get('usuario_dept'),
            "email_solicitante": session.get('usuario_email'), # <--- NOVA LINHA: Carimba o e-mail no ticket
            "titulo": dados.get('titulo'),
            "descricao": dados.get('descricao'),
            "prioridade": dados.get('prioridade'),
            "solicitante": session.get('usuario_nome'),
            "departamento": dados.get('departamento'),
            "prazo": dados.get('prazo'),
            "status": "entrada",
            "status_execucao": "pausado",
            "historico": ""
        }
        response = supabase.table('demandas').insert(nova_demanda).execute()
        disparar_n8n("novo_ticket", response.data[0])
        return jsonify({"status": "sucesso", "dados": response.data}), 201
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/demandas/<string:id>', methods=['PATCH'])
def atualizar_status(id):
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    try:
        dados = request.json
        atualizacao = {}
        ticket_atual = supabase.table('demandas').select('*').eq("id", id).execute().data[0]

        # ==========================================
        # SEGURANÇA DE BACKEND (RBAC INQUEBRÁVEL)
        # ==========================================
        usuario_dept = session.get('usuario_dept', '').upper()
        dept_destino = (ticket_atual.get('departamento') or '').upper()
        is_admin = usuario_dept in ['GERAL', 'ADMIN', 'DIRETORIA']
        
        # Apenas permite se a pessoa for do departamento que vai resolver o ticket, 
        # se for Admin, ou se a ação for apenas adicionar um comentário/histórico.
        is_apenas_historico = ('novo_historico' in dados and len(dados) == 1)
        
        if not is_admin and usuario_dept != dept_destino and not is_apenas_historico:
            return jsonify({"status": "erro", "mensagem": "Acesso Negado: Apenas a área de destino pode assumir ou alterar este chamado."}), 403
        # ==========================================

        def calcular_tempo_pendente():
            if ticket_atual.get('hora_inicio'):
                inicio = datetime.fromisoformat(ticket_atual['hora_inicio'].replace('Z', '+00:00'))
                return int((datetime.now(timezone.utc) - inicio).total_seconds() / 60)
            return 0

        evento_n8n = None

        if 'status' in dados:
            novo_status = dados.get('status')
            atualizacao['status'] = novo_status
            if novo_status == 'andamento':
                atualizacao['responsavel'] = session.get('usuario_nome')
                atualizacao['status_execucao'] = 'play'
                atualizacao['hora_inicio'] = datetime.now(timezone.utc).isoformat()
                if ticket_atual.get('status') != 'andamento': evento_n8n = "ticket_assumido"
            elif novo_status in ['pausado', 'concluido']:
                atualizacao['status_execucao'] = 'pausado'
                atualizacao['tempo_gasto'] = ticket_atual.get('tempo_gasto', 0) + calcular_tempo_pendente()
                atualizacao['hora_inicio'] = None
                if novo_status == 'concluido': evento_n8n = "ticket_concluido"
        
        elif 'status_execucao' in dados:
            execucao = dados.get('status_execucao')
            atualizacao['status_execucao'] = execucao
            if execucao == 'play':
                atualizacao['status'] = 'andamento'
                atualizacao['responsavel'] = session.get('usuario_nome')
                atualizacao['hora_inicio'] = datetime.now(timezone.utc).isoformat()
                evento_n8n = "ticket_em_execucao"
            elif execucao == 'pausado':
                atualizacao['status'] = 'pausado'
                atualizacao['tempo_gasto'] = ticket_atual.get('tempo_gasto', 0) + calcular_tempo_pendente()
                atualizacao['hora_inicio'] = None

        if 'novo_historico' in dados:
            hist_antigo = ticket_atual.get('historico', '') or ''
            atualizacao['historico'] = hist_antigo + f"• {session.get('usuario_nome')}: {dados.get('novo_historico')}\n"
            evento_n8n = "nova_interacao"

        response = supabase.table('demandas').update(atualizacao).eq("id", id).execute()
        if evento_n8n: disparar_n8n(evento_n8n, response.data[0])
        return jsonify({"status": "sucesso", "dados": response.data})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/demandas/<string:id>', methods=['DELETE'])
def deletar_demanda(id):
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    try:
        supabase.table('demandas').delete().eq("id", id).execute()
        return jsonify({"status": "sucesso"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/admin')
def admin_page():
    # Segurança: Apenas TI ou Geral acessam
    if session.get('usuario_dept') not in ['TI', 'Geral']:
        return "Acesso Negado", 403
    return render_template('admin.html')

@app.route('/api/admin/usuarios', methods=['POST'])
def criar_usuario():
    if session.get('usuario_dept') not in ['TI', 'Geral']:
        return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 403
    
    dados = request.json
    try:
        # 1. Cria o usuário no Auth do Supabase
        # Nota: Você precisará de uma senha temporária ou enviar um link de convite
        auth_response = supabase.auth.admin.create_user({
            "email": dados.get('email'),
            "password": "123456", # Recomendado: forçar reset no primeiro login
            "email_confirm": True
        })
        
        # 2. Insere os dados de perfil na sua tabela 'usuarios'
        perfil = {
            "nome": dados.get('nome'),
            "email": dados.get('email'),
            "departamento": dados.get('departamento')
        }
        supabase.table('usuarios').insert(perfil).execute()
        
        return jsonify({"status": "sucesso"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
    # Rota para listar usuários na tela admin
@app.route('/api/admin/usuarios', methods=['GET'])
def get_usuarios():
    if session.get('usuario_dept') not in ['TI', 'Geral']: return jsonify({"status": "erro"}), 403
    response = supabase.table('usuarios').select('*').execute()
    return jsonify({"status": "sucesso", "dados": response.data})

@app.route('/api/admin/usuarios/<string:email>', methods=['DELETE'])
def deletar_usuario(email):
    if session.get('usuario_dept') not in ['TI', 'Geral']: return jsonify({"status": "erro"}), 403
    try:
        # 1. Tenta remover do Auth de forma segura
        try:
            users = supabase.auth.admin.list_users()
            user = next((u for u in users.users if u.email == email), None)
            if user:
                supabase.auth.admin.delete_user(user.id)
        except Exception as auth_err:
            print("Aviso: Utilizador não encontrado no Auth ou erro de permissão:", auth_err)
            
        # 2. Remove da tabela de perfil no banco de dados
        supabase.table('usuarios').delete().eq("email", email).execute()
        return jsonify({"status": "sucesso"})
    except Exception as e:
        print("Erro fatal ao deletar:", e)
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)