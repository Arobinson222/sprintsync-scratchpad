import os
import uuid
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, abort
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Board(db.Model):
    __tablename__ = 'boards'
    id = db.Column(db.String(36), primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    columns = db.relationship('Column', backref='board', lazy=True, cascade="all, delete-orphan")

class Column(db.Model):
    __tablename__ = 'columns'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    board_id = db.Column(db.String(36), db.ForeignKey('boards.id', ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(50), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    cards = db.relationship('Card', backref='column', lazy=True, cascade="all, delete-orphan")

class Card(db.Model):
    __tablename__ = 'cards'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete="CASCADE"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    votes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def create_app(database_uri="sqlite:///sprintsync.db"):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", database_uri)
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/board/<board_id>')
    def board_view(board_id):
        target_board = Board.query.get(board_id)
        if not target_board:
            abort(404)
        return render_template('board.html', board_id=board_id)

    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200

    @app.route('/api/boards', methods=['POST'])
    def handle_board_generation():
        data = request.get_json() or {}
        title = data.get('title', 'Untitled Workspace').strip()
        column_set = data.get('columns', ['Good', 'Bad', 'Actions'])
        
        generated_id = str(uuid.uuid4())
        expiration_horizon = datetime.utcnow() + timedelta(hours=48)
        
        new_workspace = Board(id=generated_id, title=title, expires_at=expiration_horizon)
        db.session.add(new_workspace)
        
        for idx, lane_name in enumerate(column_set):
            new_lane = Column(board_id=generated_id, title=lane_name.strip(), position=idx)
            db.session.add(new_lane)
            
        db.session.commit()
        return jsonify({"board_id": generated_id}), 201

    @app.route('/api/boards/<board_id>', methods=['GET'])
    def extract_board_state(board_id):
        current_time = datetime.utcnow()
        expired_elements = Board.query.filter(Board.expires_at < current_time).all()
        for expired_item in expired_elements:
            db.session.delete(expired_item)
        db.session.commit()

        target_board = Board.query.get(board_id)
        if not target_board:
            return jsonify({"error": "Target board missing or cleanly auto-deleted"}), 404
            
        payload = {
            "id": target_board.id,
            "title": target_board.title,
            "expires_at": target_board.expires_at.isoformat(),
            "columns": []
        }
        
        sorted_lanes = sorted(target_board.columns, key=lambda x: x.position)
        for lane in sorted_lanes:
            lane_data = {"id": lane.id, "title": lane.title, "cards": []}
            for entry in lane.cards:
                lane_data["cards"].append({
                    "id": entry.id,
                    "content": entry.content,
                    "votes": entry.votes
                })
            payload["columns"].append(lane_data)
            
        return jsonify(payload), 200

    @app.route('/api/cards', methods=['POST'])
    def drop_card_element():
        data = request.get_json() or {}
        column_target = data.get('column_id')
        raw_text = data.get('content', '').strip()
        
        if not column_target or not raw_text:
            return jsonify({"error": "Malformed structural content"}), 400
            
        new_card = Card(column_id=column_target, content=raw_text)
        db.session.add(new_card)
        db.session.commit()
        return jsonify({"id": new_card.id}), 201

    @app.route('/api/cards/<int:card_id>/vote', methods=['POST'])
    def register_card_vote(card_id):
        target_card = Card.query.with_for_update().filter_by(id=card_id).first()
        if not target_card:
            return jsonify({"error": "Target content artifact lost"}), 404
            
        target_card.votes += 1
        db.session.commit()
        return jsonify({"id": target_card.id, "new_vote_count": target_card.votes}), 200

    with app.app_context():
        db.create_all()

    return app = create_app()

if __name__ == '__main__':
    application = create_app()
    application.run(host='0.0.0.0', port=5000, debug=True)
