from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime
import json
import oracledb

app = Flask(__name__)
CORS(app)

# Variáveis globais
model = None
label_encoder = None
skill_columns = None
career_names = None
dados_clean = None
model_loaded = False

# Configuração do Oracle
ORACLE_CONFIG = {
    'user': 'rm565422',
    'password': '241006', 
    'dsn': 'oracle.fiap.com.br:1521/ORCL'
}

def get_db_connection():
    """Estabelece conexão com o Oracle Database"""
    try:
        connection = oracledb.connect(
            user=ORACLE_CONFIG['user'],
            password=ORACLE_CONFIG['password'],
            dsn=ORACLE_CONFIG['dsn'],
            mode=oracledb.DEFAULT_AUTH
        )
        print("✅ Conectado ao Oracle em modo THIN!")
        return connection
    except Exception as e:
        print(f"❌ Erro ao conectar ao Oracle: {e}")
        return None

def test_oracle_connection():
    """Testa a conexão com Oracle"""
    try:
        print("🧪 Testando conexão com Oracle...")
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 'OK' FROM dual")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result and result[0] == "OK":
                print("✅ Oracle conectado via modo THIN!")
                return True
        return False
    except Exception as e:
        print(f"❌ Falha no teste de conexão: {e}")
        return False

def load_model_and_data():
    """Carrega o modelo treinado e os dados necessários"""
    global model, label_encoder, skill_columns, career_names, dados_clean, model_loaded
    
    try:
        base_path = os.path.dirname(__file__)
        
        # Verificar se arquivos existem
        required_files = ['career_model.pkl', 'career_components.pkl']
        for file in required_files:
            file_path = os.path.join(base_path, file)
            if not os.path.exists(file_path):
                print(f"❌ Arquivo não encontrado: {file_path}")
                return False
        
        # Carregar o modelo
        model_path = os.path.join(base_path, 'career_model.pkl')
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        
        # Carregar os componentes
        components_path = os.path.join(base_path, 'career_components.pkl')
        with open(components_path, 'rb') as f:
            components = pickle.load(f)
            label_encoder = components['label_encoder']
            skill_columns = components['skill_columns']
            career_names = components['career_names']
            dados_clean = components['dados_clean']
        
        # Verificar se tudo foi carregado corretamente
        if (model is not None and skill_columns is not None and 
            career_names is not None and dados_clean is not None):
            model_loaded = True
            print("✅ Modelo e dados carregados com sucesso!")
            print(f"   - Carreiras: {len(career_names)}")
            print(f"   - Skills: {len(skill_columns)}")
            return True
        else:
            print("❌ Componentes não carregados corretamente")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao carregar modelo: {e}")
        import traceback
        print(f"🔍 Detalhes: {traceback.format_exc()}")
        return False

def ensure_model_loaded():
    """Garante que o modelo está carregado antes de processar"""
    global model_loaded
    if not model_loaded:
        print("🔄 Modelo não carregado, tentando carregar agora...")
        return load_model_and_data()
    return True

def save_recommendation_oracle(user_data, recommendations):
    """Salva a recomendação no Oracle Database"""
    connection = get_db_connection()
    if not connection:
        print("❌ Não foi possível conectar ao Oracle")
        return False
    
    try:
        cursor = connection.cursor()
        
        top_career = recommendations[0]['career'] if recommendations else 'Nenhuma'
        top_compatibility = float(recommendations[0]['compatibility']) if recommendations else 0.0
        all_recommendations = ' | '.join([f"{r['career']} ({r['compatibility']}%)" for r in recommendations])
        
        cursor.execute("""
            INSERT INTO career_recommendations (
                user_skills, user_experience, user_education,
                top_recommendation, top_compatibility, all_recommendations, ip_address
            ) VALUES (:1, :2, :3, :4, :5, :6, :7)
        """, (
            json.dumps(user_data['skills']),
            user_data.get('experience', 'Não informado'),
            user_data.get('education', 'Não informado'),
            top_career,
            top_compatibility,
            all_recommendations,
            request.remote_addr
        ))
        
        connection.commit()
        print("✅ Recomendação salva no Oracle Database")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao salvar recomendação: {e}")
        return False
    finally:
        cursor.close()
        connection.close()

def get_career_skills(career_name):
    """Obtém as skills relevantes para uma carreira específica"""
    try:
        if career_names is None or dados_clean is None or skill_columns is None:
            return []
            
        career_idx = None
        for idx, name in career_names.items():
            if name == career_name:
                career_idx = idx
                break
        
        if career_idx is None:
            return []
        
        career_samples = dados_clean[dados_clean['career_encoded'] == career_idx]
        career_skills = []
        
        for skill_col in skill_columns:
            if career_samples[skill_col].sum() > 0:
                skill_name = skill_col.replace('skill_', '').replace('_', ' ').title()
                career_skills.append(skill_name)
        
        return career_skills[:8]
    except Exception as e:
        print(f"❌ Erro ao buscar skills da carreira: {e}")
        return []

# ROTAS DA API
@app.route('/')
def home():
    """Endpoint inicial"""
    db_status = "connected" if get_db_connection() else "disconnected"
    model_status = "loaded" if model_loaded else "not loaded"
    
    return jsonify({
        "message": "🚀 API de Recomendação de Carreiras",
        "status": "online",
        "database": db_status,
        "model_status": model_status,
        "endpoints": {
            "/recommend": "POST - Recebe skills e retorna recomendações",
            "/stats": "GET - Estatísticas do modelo",
            "/skills": "GET - Lista de skills disponíveis",
            "/careers": "GET - Lista de carreiras disponíveis",
            "/debug-files": "GET - Lista arquivos do servidor"
        }
    })

@app.route('/debug-files')
def debug_files():
    """Endpoint para debug - mostra arquivos no servidor"""
    import os
    current_dir = os.getcwd()
    files = []
    
    for root, dirs, filenames in os.walk('.'):
        for filename in filenames:
            files.append(os.path.join(root, filename))
    
    return jsonify({
        'current_directory': current_dir,
        'files': sorted(files)
    })

@app.route('/recommend', methods=['POST'])
def recommend_careers():
    """Endpoint principal para recomendação de carreiras"""
    try:
        # Verificar se o modelo está carregado
        if not ensure_model_loaded():
            return jsonify({
                "error": "Modelo não carregado. Serviço temporariamente indisponível."
            }), 503
        
        data = request.get_json()
        
        if not data or 'skills' not in data:
            return jsonify({
                "error": "Por favor, forneça suas skills no campo 'skills'"
            }), 400
        
        user_skills = [skill.strip().lower() for skill in data['skills']]
        user_experience = data.get('experience', '')
        user_education = data.get('education', '')
        
        if not user_skills:
            return jsonify({
                "error": "A lista de skills não pode estar vazia"
            }), 400
        
        # DEBUG: Verificar estado das variáveis
        print(f"🔍 DEBUG - skill_columns: {type(skill_columns)}, len: {len(skill_columns) if skill_columns else 'None'}")
        print(f"🔍 DEBUG - career_names: {type(career_names)}, len: {len(career_names) if career_names else 'None'}")
        print(f"🔍 DEBUG - model: {type(model)}")
        
        # Criar vetor de features para o usuário
        user_features = np.zeros(len(skill_columns))
        
        for i, skill_col in enumerate(skill_columns):
            skill_name = skill_col.replace('skill_', '').replace('_', ' ').lower()
            for user_skill in user_skills:
                if user_skill in skill_name or skill_name in user_skill:
                    user_features[i] = 1
                    break
        
        # Fazer predição
        probabilities = model.predict_proba([user_features])[0]
        
        # Obter top 5 recomendações
        top_5_indices = np.argsort(probabilities)[-5:][::-1]
        top_recommendations = []
        
        for idx in top_5_indices:
            if probabilities[idx] > 0.01:
                career_name = career_names[idx]
                compatibility = round(probabilities[idx] * 100, 2)
                
                top_recommendations.append({
                    "career": career_name,
                    "compatibility": compatibility,
                    "career_id": int(idx)
                })
        
        # Preparar dados para salvar
        user_data = {
            "skills": user_skills,
            "experience": user_experience,
            "education": user_education
        }
        
        # Tentar salvar no Oracle (opcional)
        save_success = False
        try:
            save_success = save_recommendation_oracle(user_data, top_recommendations)
        except Exception as e:
            print(f"⚠️  Não foi possível salvar no Oracle: {e}")
        
        # Adicionar detalhes para a melhor recomendação
        if top_recommendations:
            best_career = top_recommendations[0]['career']
            required_skills = get_career_skills(best_career)
            
            response = {
                "user_skills": user_skills,
                "recommendations": top_recommendations,
                "career_analysis": {
                    "best_career": best_career,
                    "required_skills": required_skills
                },
                "database_status": "saved" if save_success else "not_saved"
            }
        else:
            response = {
                "user_skills": user_skills,
                "recommendations": [],
                "message": "Não foram encontradas recomendações para suas skills.",
                "database_status": "not_saved"
            }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Erro em /recommend: {e}")
        import traceback
        print(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({
            "error": f"Erro no processamento: {str(e)}"
        }), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Retorna estatísticas do modelo"""
    try:
        total_careers = len(career_names) if career_names else 0
        total_skills = len(skill_columns) if skill_columns else 0
        
        stats_response = {
            "model_stats": {
                "total_careers": total_careers,
                "total_skills": total_skills,
                "model_loaded": model_loaded,
                "status": "operational" if model_loaded else "not_loaded"
            },
            "database_connection": "connected" if get_db_connection() else "disconnected"
        }
        
        return jsonify(stats_response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/skills', methods=['GET'])
def get_available_skills():
    """Retorna lista de skills disponíveis para uso"""
    try:
        if not ensure_model_loaded():
            return jsonify({"error": "Modelo não carregado"}), 503
            
        skills_list = []
        for skill_col in skill_columns[:50]:  # Retorna apenas as 50 primeiras
            skill_name = skill_col.replace('skill_', '').replace('_', ' ').title()
            skills_list.append(skill_name)
        
        return jsonify({
            "available_skills": skills_list,
            "total_skills": len(skills_list)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/careers', methods=['GET'])
def get_available_careers():
    """Retorna lista de carreiras disponíveis"""
    try:
        if not ensure_model_loaded():
            return jsonify({"error": "Modelo não carregado"}), 503
            
        careers_list = list(career_names.values())
        
        return jsonify({
            "available_careers": careers_list,
            "total_careers": len(careers_list)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/careers-with-skills', methods=['GET'])
def get_careers_with_skills():
    """Retorna todas as carreiras com suas skills"""
    try:
        if not ensure_model_loaded():
            return jsonify({"error": "Modelo não carregado"}), 503
        
        careers_with_skills = []
        
        for career_name in career_names.values():
            skills = get_career_skills(career_name)
            careers_with_skills.append({
                "career": career_name,
                "skills_count": len(skills),
                "skills": skills[:6]  # Limita a 6 skills por carreira
            })
        
        return jsonify({
            "total_careers": len(careers_with_skills),
            "careers": careers_with_skills
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Inicialização
def initialize():
    """Inicializa a aplicação"""
    print("🚀 Iniciando API Career Recommendation...")
    
    # Testar conexão Oracle
    if test_oracle_connection():
        print("✅ Oracle conectado")
    else:
        print("⚠️  Oracle não conectado - API funcionará sem banco")
    
    # Carregar modelo
    if load_model_and_data():
        print("🎯 API Pronta para uso!")
    else:
        print("❌ Falha ao carregar modelo - verifique os arquivos .pkl")

# Inicializar quando o app startar
@app.before_request
def before_first_request():
    """Executa antes da primeira requisição"""
    initialize()

if __name__ == '__main__':
    initialize()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 