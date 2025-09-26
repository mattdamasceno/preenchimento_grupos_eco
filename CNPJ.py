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

# Configuração da página
st.set_page_config(
    page_title="🏢 Grupos Econômicos",
    page_icon="🏢",
    layout="wide"
)

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
    
    def buscar_cnpj(self, cnpj: str):
        """Busca dados do CNPJ em APIs públicas"""
        cnpj_limpo = re.sub(r'\D', '', cnpj)
        
        # Cache simples
        if f"cnpj_{cnpj_limpo}" in st.session_state:
            return st.session_state[f"cnpj_{cnpj_limpo}"]
        
        # Tentar APIs
        for api_url in [
            f"https://www.receitaws.com.br/v1/cnpj/{cnpj_limpo}",
            f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        ]:
            try:
                response = requests.get(api_url, timeout=10)
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
                            st.session_state[f"cnpj_{cnpj_limpo}"] = result
                            return result
                    
                    # Processar Brasil API
                    else:
                        result = {
                            'razao_social': data.get('razao_social', ''),
                            'nome_fantasia': data.get('nome_fantasia', ''),
                            'atividade': data.get('cnae_fiscal_descricao', ''),
                            'situacao': data.get('descricao_situacao_cadastral', '')
                        }
                        st.session_state[f"cnpj_{cnpj_limpo}"] = result
                        return result
            except:
                continue
        
        return None
    
    def identificar_grupo(self, empresa_data: dict, gemini_key: str = None):
        """Identifica grupo econômico"""
        razao = empresa_data.get('razao_social', '').lower()
        fantasia = empresa_data.get('nome_fantasia', '').lower()
        
        # Análise por regras (sempre funciona)
        for grupo, keywords in self.grupos_conhecidos.items():
            for keyword in keywords:
                if keyword in razao or keyword in fantasia:
                    return {
                        'grupo_economico': grupo,
                        'confianca': 85,
                        'metodo': 'Regras'
                    }
        
        # Tentar Gemini se disponível
        if gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                
                for modelo in ['gemini-2.5-flash', 'gemini-2.5-pro']:
                    try:
                        model = genai.GenerativeModel(modelo)
                        prompt = f"""
Identifique o grupo econômico da empresa brasileira:
Razão Social: {empresa_data.get('razao_social', '')}
Nome Fantasia: {empresa_data.get('nome_fantasia', '')}

Grupos conhecidos: {list(self.grupos_conhecidos.keys())}

Busque por similaridade, mesmo que o nome não seja exatamente igual. Busque relações óbvias ou históricas, como "Ambev" para "Brahma" ou "Skol". Use o CNPJ para contexto se necessário, mas não dependa dele. qualquer empresa que não se encaixe em grupos conhecidos deve ser classificada como "INDEPENDENTE", mas apenas em último caso.

Resposta em JSON:
{{"grupo_economico": "NOME_GRUPO ou INDEPENDENTE", "confianca": 80}}
                        """
                        
                        response = model.generate_content(prompt)
                        json_match = re.search(r'\{.*?\}', response.text, re.DOTALL)
                        
                        if json_match:
                            result = json.loads(json_match.group())
                            return {
                                'grupo_economico': result.get('grupo_economico', 'INDEPENDENTE'),
                                'confianca': result.get('confianca', 70),
                                'metodo': f'Gemini ({modelo})'
                            }
                        break
                    except:
                        continue
            except:
                pass
        
        # Fallback
        return {
            'grupo_economico': 'INDEPENDENTE',
            'confianca': 50,
            'metodo': 'Padrão'
        }
    
    def processar_planilha(self, df: pd.DataFrame, cnpj_col: str, gemini_key: str = None):
        """Processa planilha com CNPJs"""
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, row in df.iterrows():
            progress = (idx + 1) / len(df)
            progress_bar.progress(progress)
            status_text.text(f"Processando {idx+1}/{len(df)}: {row[cnpj_col]}")
            
            cnpj = str(row[cnpj_col]).strip()
            
            # Inicializar resultado base
            resultado = {
                'cnpj_original': cnpj,
                'erro': None  # Inicializar sempre como None
            }
            
            # Validar CNPJ
            cnpj_limpo = re.sub(r'\D', '', cnpj)
            if len(cnpj_limpo) != 14:
                resultado['erro'] = 'CNPJ inválido'
            else:
                # Buscar dados
                empresa_data = self.buscar_cnpj(cnpj)
                
                if empresa_data:
                    # Identificar grupo
                    grupo_info = self.identificar_grupo(empresa_data, gemini_key)
                    
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
                else:
                    resultado.update({
                        'cnpj': cnpj_limpo,
                        'erro': 'Dados não encontrados'
                    })
            
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
        
        return pd.DataFrame(resultados)

def main():
    st.title("🏢 Identificador de Grupos Econômicos")
    st.markdown("**Upload uma planilha com CNPJs e baixe com os grupos econômicos identificados**")
    
    app = GrupoEconomicoApp()
    
    # Sidebar
    with st.sidebar:
        
        gemini_key = st.secrets["GEMINI_API_KEY"]
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
                        df_resultado = app.processar_planilha(df, cnpj_column, gemini_key)
                    
                    st.success(f"✅ Processamento concluído!")
                    
                    # Mostrar estatísticas
                    # Contar sucessos e erros de forma mais segura
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
                        # Filtrar apenas registros sem erro de forma mais segura
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

if __name__ == "__main__":
    main()