from flask import Blueprint, render_template, url_for, redirect

routes = Blueprint('routes', __name__)

@routes.route('/')
def index():
    """Rota inicial, redireciona para a tela de projetos."""
    return redirect(url_for('routes.projetos'))

@routes.route('/login')
def login():
    """Rota para a tela de login."""
    return render_template('login.html')


@routes.route('/logout')
def logout():
    """Rota para funcionalidade de logout (a implementar)."""
    return "Funcionalidade de Logout (a implementar)"

@routes.route('/projetos')
def projetos():
    """Rota para a tela de listagem de projetos."""
    projetos_lista = [ # Dados estáticos para teste inicial
        {'id': 1, 'nome_projeto': 'Projeto Exemplo 1', 'nome_propriedade': 'Fazenda Esperança', 'numero_matricula': '12345'},
        {'id': 2, 'nome_projeto': 'Projeto Exemplo 2', 'nome_propriedade': 'Sítio Alegre', 'numero_matricula': '67890'},
        {'id': 3, 'nome_projeto': 'Projeto Exemplo 3', 'nome_propriedade': 'Chácara Bonita', 'numero_matricula': '11223'}
    ]
    return render_template('projetos.html', projetos=projetos_lista)

@routes.route('/projeto/novo')
def projeto_novo():
    """Rota para a tela de criação de novo projeto."""
    return render_template('projetoNovo.html')

@routes.route('/projeto/<int:projeto_id>')
def projeto_detalhe(projeto_id):
    """Rota para a tela de detalhes de um projeto específico."""
    # Dados estáticos para teste inicial - No futuro, buscar do banco de dados pelo ID
    projeto_info = {'nome_projeto': f'Projeto Exemplo {projeto_id}', 'nome_propriedade': f'Propriedade Projeto {projeto_id}', 'numero_matricula': '998877'}
    return render_template('projetoDetalhes.html', projeto_nome=projeto_info['nome_projeto'], propriedade_nome=projeto_info['nome_propriedade'], numero_matricula=projeto_info['numero_matricula'])