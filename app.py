from flask import Flask, jsonify, request
import random
import firebase_admin
from firebase_admin import credentials, firestore
from auth import token_obrigatorio, gerar_token
from flask_cors import CORS
import os
from dotenv import load_dotenv
import json
from flasgger import Swagger

load_dotenv()

app = Flask(__name__)
app.config['SWAGGER'] = {
    'openapi': "3.0.0"
}

swagger = Swagger(app, template_file='openapi.yaml')

CORS(app, origin="*")

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

ADM_USUARIO = os.getenv("ADM_USUARIO")
ADM_SENHA = os.getenv("ADM_SENHA")

if os.getenv("VERCEL"):
    # online na vercel
    cred = credentials.Certificate(json.loads(os.getenv("FIREBASE_CREDENTIALS")))
else:
    cred = credentials.Certificate("firebase.json")

# carregar as credenciais do firebase
firebase_admin.initialize_app(cred)

# conectar ao firestore
db = firestore.client()

@app.route("/", methods=['GET'])
def root():
    return jsonify({
        "api": "academia",
        "version": "1.0",
        "Author": "Rebeca"
    }), 200

# =================================
#         ROTA DE LOGIN
# =================================
@app.route("/login", methods=["POST"])
def login():
    dados = request.get_json()
    if not dados:
        return jsonify({"error": "Envie os dados para login"}), 400

    usuario = dados.get("usuario")
    senha = dados.get("senha")

    if not usuario or not senha:
        return jsonify({"error": "Usuário e senha obrigatórios!"}), 400

    if usuario == ADM_USUARIO and senha == ADM_SENHA:
        token = gerar_token(usuario)
        return jsonify({"message": "Login realizado com sucesso!", "token": token}), 200
    return jsonify({"error": "Usuário ou senha inválidos!"}), 401

# =================================
#         ROTAS DE ALUNOS
# =================================

# rota 01 - método GET - todos os alunos
@app.route("/alunos", methods=['GET'])
def get_alunos():
    """Lista todos os alunos cadastrados"""
    alunos = []
    lista = db.collection('alunos').stream()

    for item in lista:
        alunos.append(item.to_dict())
    return jsonify(alunos), 200

# rota 02 - método GET - alunos aleatórios
@app.route("/alunos/aleatorios", methods=['GET'])
def get_aluno_random():
    """Retorna um aluno aleatório"""
    alunos = []
    lista = db.collection('alunos').stream()

    for item in lista:
        alunos.append(item.to_dict())

    if not alunos:
        return jsonify({"error": "Nenhum aluno cadastrado!"}), 404

    return jsonify(random.choice(alunos)), 200

# rota 03 - método GET - retorna aluno pelo CPF
@app.route("/alunos/<cpf>", methods=['GET'])
def get_aluno_by_cpf(cpf):
    """Retorna um aluno específico pelo CPF"""
    lista = db.collection('alunos').where('cpf', '==', cpf).stream()

    for item in lista:
        return jsonify(item.to_dict()), 200

    return jsonify({"error": "Aluno não encontrado"}), 404

# rota 04 - método POST - cadastrar novo aluno
@app.route("/alunos", methods=['POST'])
@token_obrigatorio
def post_aluno():
    """Cadastra um novo aluno na academia"""
    dados = request.get_json()

    if not dados or "nome" not in dados or "cpf" not in dados:
        return jsonify({"error": "Dados inválidos ou incompletos! É necessário nome e CPF"}), 400

    # verifica se CPF já existe
    cpf_existente = db.collection('alunos').where('cpf', '==', dados["cpf"]).limit(1).get()
    if cpf_existente:
        return jsonify({"error": "CPF já cadastrado!"}), 400

    try:
        # busca pelo contador
        contador_ref = db.collection("contador").document("controle_id")
        contador_doc = contador_ref.get()
        
        # verifica se o contador existe
        if contador_doc.exists:
            ultimo_id = contador_doc.to_dict().get("ultimo_id", 0)
        else:
            ultimo_id = 0
            contador_ref.set({"ultimo_id": 0})

        # somar 1 ao ultimo id
        novo_id = ultimo_id + 1
        # atualizar o id contador
        contador_ref.update({"ultimo_id": novo_id})

        # definir status padrão como "bloqueado"
        status = dados.get("status", "bloqueado")
        
        # validar status
        if status not in ["ativo", "bloqueado"]:
            return jsonify({"error": "Status deve ser 'ativo' ou 'bloqueado'"}), 400

        # cadastrar o novo aluno
        db.collection("alunos").add({
            "id": novo_id,
            "nome": dados["nome"],
            "cpf": dados["cpf"],
            "status": status,
            "data_cadastro": firestore.SERVER_TIMESTAMP
        })

        return jsonify({"message": "Aluno cadastrado com sucesso!"}), 201
    except Exception as e:
        return jsonify({"error": f"Falha ao cadastrar: {str(e)}"}), 400

@app.route("/alunos/<cpf>", methods=['PUT'])
@token_obrigatorio
def aluno_put(cpf):
    """Altera todos os dados de um aluno"""
    dados = request.get_json()

    # PUT é necessário enviar nome, cpf e status
    if not dados or "nome" not in dados or "cpf" not in dados or "status" not in dados:
        return jsonify({"error": "Dados inválidos ou incompletos! É necessário nome, CPF e status"}), 400

    # validar status
    if dados["status"] not in ["ativo", "bloqueado"]:
        return jsonify({"error": "Status deve ser 'ativo' ou 'bloqueado'"}), 400

    try:
        docs = db.collection("alunos").where("cpf", "==", cpf).limit(1).get()
        if not docs:
            return jsonify({"error": "Aluno não encontrado!"}), 404

        # verifica se o novo CPF já existe em outro aluno
        if dados["cpf"] != cpf:
            cpf_existente = db.collection('alunos').where('cpf', '==', dados["cpf"]).limit(1).get()
            if cpf_existente:
                return jsonify({"error": "Novo CPF já está cadastrado para outro aluno!"}), 400

        # pega o 1º e único documento da lista
        for doc in docs:
            doc_ref = db.collection("alunos").document(doc.id)
            doc_ref.update({
                "nome": dados['nome'],
                "cpf": dados['cpf'],
                "status": dados['status']
            })
        return jsonify({"message": "Aluno alterado com sucesso!"}), 200
    except Exception as e:
        return jsonify({"error": f"Falha na alteração: {str(e)}"}), 400

# rota 06 - método PATCH - alteração parcial
@app.route("/alunos/<cpf>", methods=['PATCH'])
@token_obrigatorio
def aluno_patch(cpf):
    """Altera dados específicos de um aluno"""
    dados = request.get_json()

    if not dados:
        return jsonify({"error": "Envie os dados para alteração!"}), 400

    try:
        docs = db.collection("alunos").where("cpf", "==", cpf).limit(1).get()
        if not docs:
            return jsonify({"error": "Aluno não encontrado!"}), 404

        doc_ref = db.collection("alunos").document(docs[0].id)
        update_aluno = {}

        if "nome" in dados:
            update_aluno["nome"] = dados["nome"]

        if "cpf" in dados:
            # verifica se o novo CPF já existe
            if dados["cpf"] != cpf:
                cpf_existente = db.collection('alunos').where('cpf', '==', dados["cpf"]).limit(1).get()
                if cpf_existente:
                    return jsonify({"error": "Novo CPF já está cadastrado para outro aluno!"}), 400
            update_aluno["cpf"] = dados["cpf"]

        if "status" in dados:
            if dados["status"] not in ["ativo", "bloqueado"]:
                return jsonify({"error": "Status deve ser 'ativo' ou 'bloqueado'"}), 400
            update_aluno["status"] = dados["status"]

        if not update_aluno:
            return jsonify({"error": "Nenhum dado válido para alteração!"}), 400

        # atualizar o firestore
        doc_ref.update(update_aluno)

        return jsonify({"message": "Aluno alterado com sucesso!"}), 200
    except Exception as e:
        return jsonify({"error": f"Falha na alteração: {str(e)}"}), 400

# rota 07 - método DELETE - excluir aluno
@app.route("/alunos/<cpf>", methods=['DELETE'])
@token_obrigatorio
def delete_aluno(cpf):
    """Exclui um aluno da academia"""
    docs = db.collection("alunos").where("cpf", "==", cpf).limit(1).get()

    if not docs:
        return jsonify({"error": "Aluno não encontrado!"}), 404

    doc_ref = db.collection("alunos").document(docs[0].id)
    doc_ref.delete()
    return jsonify({"message": "Aluno excluído com sucesso!"}), 200

# rota extra - método GET - filtrar alunos por status
@app.route("/alunos/status/<status>", methods=['GET'])
def get_alunos_by_status(status):
    """Retorna alunos filtrados por status (ativo ou bloqueado)"""
    if status not in ["ativo", "bloqueado"]:
        return jsonify({"error": "Status deve ser 'ativo' ou 'bloqueado'"}), 400

    alunos = []
    lista = db.collection('alunos').where('status', '==', status).stream()

    for item in lista:
        alunos.append(item.to_dict())

    if not alunos:
        return jsonify({"message": f"Nenhum aluno com status '{status}' encontrado"}), 404

    return jsonify(alunos), 200

# rota extra - método PUT - alterar status do aluno (pagar/renegociar)
@app.route("/alunos/<cpf>/status", methods=['PUT'])
@token_obrigatorio
def alterar_status_aluno(cpf):
    """Altera apenas o status do aluno (pagamento)"""
    dados = request.get_json()

    if not dados or "status" not in dados:
        return jsonify({"error": "Envie o novo status!"}), 400

    if dados["status"] not in ["ativo", "bloqueado"]:
        return jsonify({"error": "Status deve ser 'ativo' ou 'bloqueado'"}), 400

    try:
        docs = db.collection("alunos").where("cpf", "==", cpf).limit(1).get()
        if not docs:
            return jsonify({"error": "Aluno não encontrado!"}), 404

        doc_ref = db.collection("alunos").document(docs[0].id)
        doc_ref.update({"status": dados["status"]})

        mensagem = "Aluno ativado com sucesso!" if dados["status"] == "ativo" else "Aluno bloqueado com sucesso!"
        return jsonify({"message": mensagem}), 200
    except Exception as e:
        return jsonify({"error": f"Falha na alteração: {str(e)}"}), 400

# =================================
#         TRATAMENTO DE ERROS
# =================================

@app.errorhandler(404)
def erro404(error):
    return jsonify({"error": "Rota não encontrada"}), 404

@app.errorhandler(500)
def erro500(error):
    return jsonify({"error": "Servidor interno com falhas!"}), 500

if __name__ == "__main__":
    app.run(debug=True)