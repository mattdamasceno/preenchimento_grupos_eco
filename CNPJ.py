#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import os
import requests
import re
import time
from datetime import datetime
import google.generativeai as genai
import json
import io
import logging
from io import StringIO

# Configuração da página
st.set_page_config(
    page_title="🏢 Grupos Econômicos",
    page_icon="🏢",
    layout="wide"
)

# Configurar logging
class StreamlitLogHandler(logging.Handler):
    """Handler customizado para exibir logs no Streamlit"""
    def __init__(self):
        super().__init__()
        self.logs = []
    
    def emit(self, record):
        log_entry = self.format(record)
        self.logs.append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'level': record.levelname,
            'message': log_entry
        })

# Configurar logger
logger = logging.getLogger('GrupoEconomicoApp')
logger.setLevel(logging.DEBUG)

# Handler para Streamlit
streamlit_handler = StreamlitLogHandler()
streamlit_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
logger.addHandler(streamlit_handler)

# Handler para console (opcional)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

class GrupoEconomicoApp:
    def __init__(self):
        self.grupos_conhecidos = {
            "AMBEV": ["ambev", "brahma", "skol", "antarctica", "anheuser"],
            "VALE": ["vale", "samarco"],
            "PETROBRAS": ["petrobras", "br distribuidora"],
            "ITAU": ["itau", "unibanco"],
            "BRADESCO": ["bradesco"],
            "JBS": ["jbs", "friboi", "seara"],
            "NATURA": ["natura", "avon"],
            "MAGAZINE LUIZA": ["magalu", "magazine luiza"],
            "SUZANO": ["suzano"],
            "GERDAU": ["gerdau"]
        }
        logger.info(f"App inicializado com {len(self.grupos_conhecidos)} grupos conhecidos")
    
    def buscar_cnpj(self, cnpj: str):
        """Busca dados do CNPJ em APIs públicas"""
        cnpj_limpo = re.sub(r'\D', '', cnpj)
        logger.debug(f"Buscando CNPJ: {cnpj_limpo}")
        
        # Cache simples
        if f"cnpj_{cnpj_limpo}" in st.session_state:
            logger.debug(f"CNPJ {cnpj_limpo} encontrado no cache")
            return st.session_state[f"cnpj_{cnpj_limpo}"]
        
        # Tentar APIs
        for api_url in [
            f"https://www.receitaws.com.br/v1/cnpj/{cnpj_limpo}",
            f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        ]:
            try:
                logger.debug(f"Tentando API: {api_url}")
                response = requests.get(api_url, timeout=10)
                logger.debug(f"Status da resposta: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Processar ReceitaWS
                    if "receitaws" in api_url:
                        if data.get('status') == 'OK':
                            result = {
                                'razao_social': data.get('nome', ''),
                                'nome_fantasia': data.get('fantasia', ''),
                                'atividade': data.get('atividade_principal', {}).get('text', '') if isinstance(data.get('atividade_principal'), dict) else str(data.get('atividade_principal', '')),
                                'situacao': data.get('situacao', '')
                            }
                            logger.info(f"✅ Dados encontrados (ReceitaWS): {result['razao_social']}")
                            st.session_state[f"cnpj_{cnpj_limpo}"] = result
                            return result
                        else:
                            logger.warning(f"ReceitaWS retornou status: {data.get('status')}")
                    
                    # Processar Brasil API
                    else:
                        result = {
                            'razao_social': data.get('razao_social', ''),
                            'nome_fantasia': data.get('nome_fantasia', ''),
                            'atividade': data.get('cnae_fiscal_descricao', ''),
                            'situacao': data.get('descricao_situacao_cadastral', '')
                        }
                        logger.info(f"✅ Dados encontrados (BrasilAPI): {result['razao_social']}")
                        st.session_state[f"cnpj_{cnpj_limpo}"] = result
                        return result
            except Exception as e:
                logger.error(f"Erro ao buscar em {api_url}: {str(e)}")
                continue
        
        logger.warning(f"❌ Nenhuma API retornou dados para CNPJ {cnpj_limpo}")
        return None
    
    def buscar_perplexity(self, empresa_data: dict, perplexity_key: str):
        """Busca informações sobre grupo econômico via Perplexity API"""
        try:
            logger.debug("Tentando Perplexity API...")
            
            headers = {
                "Authorization": f"Bearer {perplexity_key}",
                "Content-Type": "application/json"
            }
            
            razao = empresa_data.get('razao_social', '')
            fantasia = empresa_data.get('nome_fantasia', '')
            
            payload = {
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": "Você é um assistente especializado em identificar grupos econômicos brasileiros. Responda APENAS com JSON no formato: {\"grupo_economico\": \"NOME_DO_GRUPO\", \"confianca\": 85}"
                    },
                    {
                        "role": "user",
                        "content": f"""Identifique o grupo econômico desta empresa brasileira:
Razão Social: {razao}
Nome Fantasia: {fantasia}

Grupos conhecidos: {list(self.grupos_conhecidos.keys())}

Se a empresa pertence a algum desses grupos ou você tem certeza de outro grupo econômico relevante, informe. Se for independente ou você não tiver certeza, retorne "INDEPENDENTE".

Responda APENAS com JSON válido."""
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 200
            }
            
            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                json=payload,
                headers=headers,
                timeout=15
            )
            
            logger.debug(f"Perplexity status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                logger.debug(f"Resposta Perplexity: {content[:200]}...")
                
                # Tentar extrair JSON
                json_match = re.search(r'\{.*?\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    grupo = result.get('grupo_economico', 'INDEPENDENTE')
                    confianca = result.get('confianca', 75)
                    
                    logger.info(f"✅ Grupo identificado por Perplexity: {grupo} ({confianca}%)")
                    return {
                        'grupo_economico': grupo,
                        'confianca': confianca,
                        'metodo': 'Perplexity'
                    }
                else:
                    logger.warning("Perplexity não retornou JSON válido")
            else:
                logger.error(f"Erro Perplexity: {response.status_code} - {response.text[:200]}")
        except Exception as e:
            logger.error(f"Erro ao usar Perplexity: {str(e)}")
        
        return None
    
    def identificar_grupo(self, empresa_data: dict, gemini_key: str = None, perplexity_key: str = None):
        """Identifica grupo econômico"""
        razao = empresa_data.get('razao_social', '').lower()
        fantasia = empresa_data.get('nome_fantasia', '').lower()
        
        logger.debug(f"Identificando grupo para: {razao} / {fantasia}")
        
        # Análise por regras (sempre funciona)
        for grupo, keywords in self.grupos_conhecidos.items():
            for keyword in keywords:
                if keyword in razao or keyword in fantasia:
                    logger.info(f"✅ Grupo identificado por regras: {grupo} (keyword: {keyword})")
                    return {
                        'grupo_economico': grupo,
                        'confianca': 85,
                        'metodo': 'Regras'
                    }
        
        logger.debug("Nenhum grupo identificado por regras, tentando AI...")
        
        # PRIORIDADE 1: Perplexity (mais confiável para pesquisa)
        if perplexity_key:
            resultado = self.buscar_perplexity(empresa_data, perplexity_key)
            if resultado:
                return resultado
        else:
            logger.warning("Chave do Perplexity não fornecida")
        
        # PRIORIDADE 2: Gemini (fallback)
        if gemini_key:
            try:
                logger.debug("Tentando Gemini API...")
                genai.configure(api_key=gemini_key)
                
                for modelo in ['gemini-2.5-flash', 'gemini-2.5-pro']:
                    try:
                        logger.debug(f"Tentando modelo: {modelo}")
                        model = genai.GenerativeModel(modelo)
                        prompt = f"""
Identifique o grupo econômico da empresa brasileira:
Razão Social: {empresa_data.get('razao_social', '')}
Nome Fantasia: {empresa_data.get('nome_fantasia', '')}

Grupos conhecidos: {list(self.grupos_conhecidos.keys())}

Busque por similaridade, mesmo que o nome não seja exatamente igual. Busque relações óbvias ou históricas, como "Ambev" para "Brahma" ou "Skol". Use o CNPJ para contexto se necessário, mas não dependa dele. qualquer empresa que não se encaixe em grupos conhecidos deve ser classificada como "INDEPENDENTE", mas apenas em último caso.

Responda APENAS com JSON válido:
{{"grupo_economico": "NOME_GRUPO ou INDEPENDENTE", "confianca": 80}}
                        """
                        
                        logger.debug("Enviando prompt para Gemini...")
                        response = model.generate_content(prompt)
                        logger.debug(f"Resposta do Gemini: {response.text[:200]}...")
                        
                        json_match = re.search(r'\{.*?\}', response.text, re.DOTALL)
                        
                        if json_match:
                            result = json.loads(json_match.group())
                            logger.info(f"✅ Grupo identificado por Gemini ({modelo}): {result.get('grupo_economico')} ({result.get('confianca')}%)")
                            return {
                                'grupo_economico': result.get('grupo_economico', 'INDEPENDENTE'),
                                'confianca': result.get('confianca', 70),
                                'metodo': f'Gemini ({modelo})'
                            }
                        else:
                            logger.warning(f"Gemini não retornou JSON válido")
                        break
                    except Exception as e:
                        logger.error(f"Erro com modelo {modelo}: {str(e)}")
                        continue
            except Exception as e:
                logger.error(f"Erro ao usar Gemini: {str(e)}")
        else:
            logger.warning("Chave do Gemini não fornecida")
        
        # Fallback final
        logger.warning("⚠️ Caindo no fallback - classificando como INDEPENDENTE")
        return {
            'grupo_economico': 'INDEPENDENTE',
            'confianca': 50,
            'metodo': 'Padrão'
        }
    
    def processar_planilha(self, df: pd.DataFrame, cnpj_col: str, gemini_key: str = None, perplexity_key: str = None):
        """Processa planilha com CNPJs"""
        logger.info(f"Iniciando processamento de {len(df)} CNPJs")
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, row in df.iterrows():
            progress = (idx + 1) / len(df)
            progress_bar.progress(progress)
            status_text.text(f"Processando {idx+1}/{len(df)}: {row[cnpj_col]}")
            
            cnpj = str(row[cnpj_col]).strip()
            logger.info(f"\n{'='*60}\nProcessando linha {idx+1}: {cnpj}")
            
            # Inicializar resultado base
            resultado = {
                'cnpj_original': cnpj,
                'erro': None
            }
            
            # Validar CNPJ
            cnpj_limpo = re.sub(r'\D', '', cnpj)
            if len(cnpj_limpo) != 14:
                logger.error(f"CNPJ inválido: {cnpj} (tamanho: {len(cnpj_limpo)})")
                resultado['erro'] = 'CNPJ inválido'
            else:
                # Buscar dados
                empresa_data = self.buscar_cnpj(cnpj)
                
                if empresa_data:
                    # Identificar grupo
                    grupo_info = self.identificar_grupo(empresa_data, gemini_key, perplexity_key)
                    
                    resultado.update({
                        'cnpj': cnpj_limpo,
                        'razao_social': empresa_data['razao_social'],
                        'nome_fantasia': empresa_data['nome_fantasia'],
                        'grupo_economico': grupo_info['grupo_economico'],
                        'confianca': grupo_info['confianca'],
                        'metodo_analise': grupo_info['metodo'],
                        'atividade': empresa_data['atividade'],
                        'situacao': empresa_data['situacao']
                    })
                    logger.info(f"✅ Resultado: {grupo_info['grupo_economico']} ({grupo_info['confianca']}%) via {grupo_info['metodo']}")
                else:
                    resultado.update({
                        'cnpj': cnpj_limpo,
                        'erro': 'Dados não encontrados'
                    })
                    logger.error(f"❌ Dados não encontrados para CNPJ {cnpj}")
            
            # Adicionar dados originais da planilha
            for col in df.columns:
                if col != cnpj_col:
                    resultado[f'original_{col}'] = row[col]
            
            resultados.append(resultado)
            
            # Pausa para não sobrecarregar APIs
            if idx < len(df) - 1:
                time.sleep(1)
        
        progress_bar.empty()
        status_text.empty()
        logger.info(f"Processamento concluído: {len(resultados)} registros")
        
        return pd.DataFrame(resultados)

def main():
    st.title("🏢 Identificador de Grupos Econômicos")
    st.markdown("**Upload uma planilha com CNPJs e baixe com os grupos econômicos identificados**")
    
    app = GrupoEconomicoApp()
    
    # Sidebar
    with st.sidebar:
        gemini_key = st.secrets.get("GEMINI_API_KEY")
        perplexity_key = st.secrets.get("PERPLEXITY_API_KEY")
        
        # Indicador de APIs configuradas
        st.markdown("**🔑 APIs Configuradas:**")
        st.markdown(f"{'✅' if perplexity_key else '❌'} Perplexity (Prioridade 1)")
        st.markdown(f"{'✅' if gemini_key else '❌'} Gemini (Fallback)")
        
        st.markdown("---")
        st.markdown("**🐛 Debug**")
        show_logs = st.checkbox("Mostrar logs detalhados", value=False)
        
        if st.button("🗑️ Limpar cache"):
            for key in list(st.session_state.keys()):
                if key.startswith('cnpj_'):
                    del st.session_state[key]
            st.success("Cache limpo!")
            logger.info("Cache limpo manualmente")
        
        st.markdown("---")
        st.markdown("**📋 Como usar:**")
        st.markdown("1. Faça upload da planilha Excel")
        st.markdown("2. Selecione a coluna com CNPJs")
        st.markdown("3. Processe e baixe resultado")
    
    # Área principal
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.header("📁 Upload da Planilha")
        
        # Upload do arquivo
        uploaded_file = st.file_uploader(
            "Escolha um arquivo Excel (.xlsx, .xls)",
            type=['xlsx', 'xls'],
            help="Sua planilha deve ter pelo menos uma coluna com CNPJs"
        )
        
        if uploaded_file:
            try:
                # Ler planilha
                df = pd.read_excel(uploaded_file)
                st.success(f"✅ Planilha carregada: {len(df)} linhas, {len(df.columns)} colunas")
                logger.info(f"Planilha carregada: {len(df)} linhas")
                
                # Mostrar preview
                with st.expander("👁️ Preview da planilha"):
                    st.dataframe(df.head())
                
                # Selecionar coluna do CNPJ
                cnpj_column = st.selectbox(
                    "📋 Selecione a coluna que contém os CNPJs:",
                    options=df.columns.tolist(),
                    help="Escolha a coluna com os números de CNPJ"
                )
                
                # Botão processar
                if st.button("🚀 Processar Planilha", type="primary", use_container_width=True):
                    
                    with st.spinner("Processando CNPJs..."):
                        df_resultado = app.processar_planilha(df, cnpj_column, gemini_key, perplexity_key)
                    
                    st.success(f"✅ Processamento concluído!")
                    
                    # Mostrar estatísticas
                    total_registros = len(df_resultado)
                    registros_com_erro = df_resultado['erro'].notna().sum()
                    sucessos = total_registros - registros_com_erro
                    erros = registros_com_erro
                    
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("Total", len(df_resultado))
                    with col_stat2:
                        st.metric("Sucessos", sucessos)
                    with col_stat3:
                        st.metric("Erros", erros)
                    
                    # Mostrar resultado
                    st.header("📊 Resultado")
                    
                    # Colunas principais para visualização
                    colunas_principais = ['cnpj_original', 'razao_social', 'grupo_economico', 'confianca']
                    colunas_disponiveis = [col for col in colunas_principais if col in df_resultado.columns]
                    
                    if colunas_disponiveis:
                        st.dataframe(df_resultado[colunas_disponiveis], use_container_width=True)
                    
                    # Gráfico de grupos (se houver sucessos)
                    if sucessos > 0:
                        registros_validos = df_resultado[df_resultado['erro'].isna()]
                        
                        if len(registros_validos) > 0 and 'grupo_economico' in registros_validos.columns:
                            grupos_count = registros_validos['grupo_economico'].value_counts()
                            if len(grupos_count) > 0:
                                st.subheader("📊 Distribuição por Grupos")
                                st.bar_chart(grupos_count)
                    
                    # Download
                    st.header("💾 Download")
                    
                    # Preparar Excel
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_resultado.to_excel(writer, index=False, sheet_name='Resultado')
                    
                    st.download_button(
                        label="📥 Baixar Excel com Resultados",
                        data=buffer.getvalue(),
                        file_name=f"grupos_economicos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )
                    
                    # Detalhes completos
                    with st.expander("🔍 Ver dados completos"):
                        st.dataframe(df_resultado, use_container_width=True)
                
            except Exception as e:
                logger.exception("Erro crítico no processamento")
                st.error(f"❌ Erro ao processar planilha: {e}")
    
    with col2:
        st.header("ℹ️ Informações")
        
        # Template de exemplo
        st.markdown("**📋 Exemplo de planilha:**")
        
        exemplo_data = {
            'cnpj': ['33.000.167/0001-01', '02.916.265/0001-60'],
            'nome_empresa': ['Vale S.A.', 'Ambev S.A.']
        }
        exemplo_df = pd.DataFrame(exemplo_data)
        st.dataframe(exemplo_df, hide_index=True)
        
        # Download template
        buffer_template = io.BytesIO()
        exemplo_df.to_excel(buffer_template, index=False)
        
        st.download_button(
            "📄 Baixar Template",
            data=buffer_template.getvalue(),
            file_name="template_cnpjs.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.markdown("---")
        st.markdown("**🎯 Grupos identificados:**")
        for grupo in list(app.grupos_conhecidos.keys())[:8]:
            st.markdown(f"• {grupo}")
        st.markdown("• E outros...")
    
    # Exibir logs se habilitado
    if show_logs:
        st.markdown("---")
        st.header("🐛 Logs de Debug")
        
        if streamlit_handler.logs:
            # Criar DataFrame com os logs
            logs_df = pd.DataFrame(streamlit_handler.logs)
            
            # Filtros
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                level_filter = st.multiselect(
                    "Filtrar por nível:",
                    options=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                    default=['INFO', 'WARNING', 'ERROR']
                )
            
            with col_filter2:
                search_term = st.text_input("Buscar nos logs:", "")
            
            # Aplicar filtros
            filtered_logs = logs_df[logs_df['level'].isin(level_filter)]
            if search_term:
                filtered_logs = filtered_logs[filtered_logs['message'].str.contains(search_term, case=False, na=False)]
            
            # Exibir logs
            st.dataframe(
                filtered_logs,
                use_container_width=True,
                height=400
            )
            
            # Botão para limpar logs
            if st.button("🗑️ Limpar logs"):
                streamlit_handler.logs.clear()
                st.rerun()
        else:
            st.info("Nenhum log ainda. Processe uma planilha para ver os logs.")

if __name__ == "__main__":
    main()
