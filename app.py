from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime
import json
import oracledb
import os

app = Flask(__name__)
CORS(app)

# Variáveis globais
model = None
label_encoder = None
skill_columns = None
career_names = None
dados_clean = None

# Configuração DIRETA do Oracle - SEM variáveis de ambiente
ORACLE_CONFIG = {
    'user': 'rm565422',  # Coloque seu usuário aqui
    'password': '241006',  # Coloque sua senha aqui
    'dsn': 'oracle.fiap.com.br:1521/ORCL'  # Para Oracle XE
}

def get_db_connection():
    """Conexão direta com Oracle - sem variáveis de ambiente"""
    try:
        connection = oracledb.connect(
            user=ORACLE_CONFIG['user'],
            password=ORACLE_CONFIG['password'],
            dsn=ORACLE_CONFIG['dsn']
        )
        print(f"✅ Conectado ao Oracle: {ORACLE_CONFIG['user']}@{ORACLE_CONFIG['dsn']}")
        return connection
        
    except oracledb.Error as e:
        error, = e.args
        print(f"❌ Erro Oracle: {error.code} - {error.message}")
        print("💡 Dicas:")
        print("   - Verifique se o Oracle está rodando")
        print("   - Confirme usuário/senha")
        print("   - Tente DSN: localhost:1521/XEPDB1 para Oracle 21c XE")
        return None
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return None

def create_tables():
    """Cria as tabelas necessárias no Oracle"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Tabela de recomendações
            cursor.execute("""
                BEGIN
                    EXECUTE IMMEDIATE '
                        CREATE TABLE career_recommendations (
                            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            user_skills CLOB,
                            user_experience VARCHAR2(200),
                            user_education VARCHAR2(200),
                            top_recommendation VARCHAR2(200),
                            top_compatibility NUMBER(5,2),
                            all_recommendations CLOB,
                            ip_address VARCHAR2(45)
                        )
                    ';
                EXCEPTION
                    WHEN OTHERS THEN
                        IF SQLCODE != -955 THEN -- tabela já existe
                            RAISE;
                        END IF;
                END;
            """)
            
            # Tabela de logs da API
            cursor.execute("""
                BEGIN
                    EXECUTE IMMEDIATE '
                        CREATE TABLE api_usage_logs (
                            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            endpoint VARCHAR2(100),
                            method VARCHAR2(10),
                            response_time NUMBER(10,2),
                            status_code NUMBER(3)
                        )
                    ';
                EXCEPTION
                    WHEN OTHERS THEN
                        IF SQLCODE != -955 THEN
                            RAISE;
                        END IF;
                END;
            """)
            
            # Tabela de skills das carreiras
            cursor.execute("""
                BEGIN
                    EXECUTE IMMEDIATE '
                        CREATE TABLE career_skills (
                            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            career_id NUMBER,
                            career_name VARCHAR2(200),
                            required_skills CLOB,
                            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ';
                EXCEPTION
                    WHEN OTHERS THEN
                        IF SQLCODE != -955 THEN
                            RAISE;
                        END IF;
                END;
            """)
            
            connection.commit()
            print("✅ Tabelas criadas/verificadas no Oracle!")
            
        except Exception as e:
            print(f"❌ Erro ao criar tabelas: {e}")
        finally:
            cursor.close()
            connection.close()

def test_oracle_connection():
    """Testa a conexão com Oracle"""
    try:
        print("🧪 Testando conexão com Oracle...")
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT '✅ Oracle conectado!', banner FROM v$version WHERE rownum = 1")
            result = cursor.fetchone()
            print(f"{result[0]} - {result[1]}")
            cursor.close()
            conn.close()
            return True
        return False
    except Exception as e:
        print(f"❌ Falha no teste de conexão: {e}")
        return False

import os

def load_model_and_data():
    """Carrega o modelo treinado e os dados necessários"""
    global model, label_encoder, skill_columns, career_names, dados_clean
    
    try:
        base_path = os.path.dirname(__file__)
        model_path = os.path.join(base_path, 'career_model.pkl')
        components_path = os.path.join(base_path, 'career_components.pkl')
        
        # Carregar o modelo
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        
        # Carregar os outros componentes
        with open(components_path, 'rb') as f:
            components = pickle.load(f)
            label_encoder = components['label_encoder']
            skill_columns = components['skill_columns']
            career_names = components['career_names']
            dados_clean = components['dados_clean']
        
        print("✅ Modelo e dados carregados com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao carregar modelo: {e}")
        return False

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

def get_recommendation_stats_oracle():
    """Obtém estatísticas do Oracle Database"""
    connection = get_db_connection()
    if not connection:
        return None
    
    try:
        cursor = connection.cursor()
        
        # Total de recomendações
        cursor.execute("SELECT COUNT(*) FROM career_recommendations")
        total_recommendations = cursor.fetchone()[0]
        
        # Carreira mais recomendada
        cursor.execute("""
            SELECT top_recommendation, COUNT(*) as count 
            FROM career_recommendations 
            WHERE top_recommendation != 'Nenhuma'
            GROUP BY top_recommendation 
            ORDER BY count DESC 
            FETCH FIRST 1 ROWS ONLY
        """)
        top_career_result = cursor.fetchone()
        top_career = top_career_result[0] if top_career_result else "Nenhuma"
        top_career_count = top_career_result[1] if top_career_result else 0
        
        # Compatibilidade média
        cursor.execute("""
            SELECT AVG(top_compatibility) FROM career_recommendations 
            WHERE top_compatibility > 0
        """)
        avg_compatibility = cursor.fetchone()[0] or 0
        
        return {
            'total_recommendations': total_recommendations,
            'most_recommended_career': top_career,
            'most_recommended_count': top_career_count,
            'average_compatibility': round(float(avg_compatibility), 2)
        }
        
    except Exception as e:
        print(f"❌ Erro ao buscar estatísticas: {e}")
        return None
    finally:
        cursor.close()
        connection.close()

def get_career_skills(career_name):
    """Obtém as skills relevantes para uma carreira específica"""
    try:
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
    except:
        return []

@app.route('/')
def home():
    """Endpoint inicial"""
    db_status = "connected" if get_db_connection() else "disconnected"
    return jsonify({
        "message": "🚀 API de Recomendação de Carreiras",
        "status": "online",
        "database": db_status,
        "oracle_config": {
            "user": ORACLE_CONFIG['user'],
            "dsn": ORACLE_CONFIG['dsn']
        },
        "endpoints": {
            "/recommend": "POST - Recebe skills e retorna recomendações",
            "/stats": "GET - Estatísticas do modelo e recomendações",
            "/skills": "GET - Lista de skills disponíveis",
            "/careers": "GET - Lista de carreiras disponíveis"
        }
    })

@app.route('/recommend', methods=['POST'])
def recommend_careers():
    """Endpoint principal para recomendação de carreiras"""
    try:
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
        
        # Preparar dados para salvar
        user_data = {
            "skills": user_skills,
            "experience": user_experience,
            "education": user_education
        }
        
        # Salvar recomendação no Oracle
        save_success = save_recommendation_oracle(user_data, top_recommendations)
        
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
                "database_status": "saved" if save_success else "failed"
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
        return jsonify({
            "error": f"Erro no processamento: {str(e)}"
        }), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Retorna estatísticas do modelo e do banco de dados"""
    try:
        total_careers = len(career_names) if career_names else 0
        total_skills = len(skill_columns) if skill_columns else 0
        
        # Estatísticas do Oracle
        oracle_stats = get_recommendation_stats_oracle()
        
        stats_response = {
            "model_stats": {
                "total_careers": total_careers,
                "total_skills": total_skills,
                "model_loaded": model is not None
            },
            "database_stats": oracle_stats if oracle_stats else {"error": "Não foi possível conectar ao banco"},
            "database_connection": "connected" if get_db_connection() else "disconnected",
            "oracle_config": ORACLE_CONFIG
        }
        
        return jsonify(stats_response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/skills', methods=['GET'])
def get_available_skills():
    """Retorna lista de skills disponíveis para uso"""
    try:
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
        careers_list = list(career_names.values()) if career_names else []
        
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
        if model is None:
            load_model_and_data()
        
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
        create_tables()
    else:
        print("⚠️  Oracle não conectado - API funcionará sem banco")
    
    # Carregar modelo
    if load_model_and_data():
        print("🎯 API Pronta para uso!")
    else:
        print("❌ Modelo não carregado - verifique os arquivos .pkl")

if __name__ == '__main__':
    initialize()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)