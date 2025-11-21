from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import pickle
import os
import json

app = Flask(__name__)
CORS(app)

# Variáveis globais
model = None
skill_columns = None
career_names = None
dados_clean = None
model_loaded = False

def load_model_and_data():
    """Carrega o modelo treinado e os dados necessários"""
    global model, skill_columns, career_names, dados_clean, model_loaded
    
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
        print(f"📦 Carregando modelo de: {model_path}")
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        
        # Carregar os componentes
        components_path = os.path.join(base_path, 'career_components.pkl')
        print(f"📦 Carregando componentes de: {components_path}")
        with open(components_path, 'rb') as f:
            components = pickle.load(f)
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
    return jsonify({
        "message": "🚀 API de Recomendação de Carreiras",
        "status": "online",
        "model_status": "loaded" if model_loaded else "not loaded",
        "endpoints": {
            "/recommend": "POST - Recebe skills e retorna recomendações",
            "/stats": "GET - Estatísticas do modelo",
            "/skills": "GET - Lista de skills disponíveis",
            "/careers": "GET - Lista de carreiras disponíveis"
        }
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
                }
            }
        else:
            response = {
                "user_skills": user_skills,
                "recommendations": [],
                "message": "Não foram encontradas recomendações para suas skills."
            }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Erro em /recommend: {e}")
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
                "model_loaded": model_loaded
            }
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
        for skill_col in skill_columns[:50]:
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

# Inicialização
def initialize():
    """Inicializa a aplicação"""
    print("🚀 Iniciando API Career Recommendation...")
    
    # Carregar modelo
    if load_model_and_data():
        print("🎯 API Pronta para uso!")
    else:
        print("❌ Falha ao carregar modelo")

# Inicializar quando o app startar
with app.app_context():
    initialize()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)