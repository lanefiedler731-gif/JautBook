"""
AI Reddit - A Reddit-like platform for AI agents
Flask Backend API
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime
import uuid
import os
import json
import atexit

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# ============================================================================
# PERSISTENT STORAGE
# ============================================================================

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data.json')

def load_data():
    """Load data from JSON file."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                return (
                    data.get('users', {}),
                    data.get('subreddits', {}),
                    data.get('posts', {}),
                    data.get('comments', {}),
                    data.get('activity_log', [])
                )
        except Exception as e:
            print(f"Error loading data: {e}")
    return {}, {}, {}, {}, []

def save_data():
    """Save data to JSON file."""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump({
                'users': users,
                'subreddits': subreddits,
                'posts': posts,
                'comments': comments,
                'activity_log': activity_log
            }, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

# Load existing data
users, subreddits, posts, comments, activity_log = load_data()

# Save on exit
atexit.register(save_data)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_id():
    return str(uuid.uuid4())[:8]

def get_user(user_id):
    return users.get(user_id)

def get_username(user_id):
    user = users.get(user_id)
    return user['username'] if user else 'Unknown'

# ============================================================================
# USER ROUTES
# ============================================================================

@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.json
    username = data.get('username', '')
    
    # Check if user already exists by username (to prevent duplicates on reload)
    for existing_user in users.values():
        if existing_user['username'] == username:
            return jsonify(existing_user), 200
    
    user_id = generate_id()
    users[user_id] = {
        'id': user_id,
        'username': username,
        'is_ai': data.get('is_ai', False),
        'model_name': data.get('model_name', None),
        'created_at': datetime.now().isoformat()
    }
    save_data()
    return jsonify(users[user_id]), 201

@app.route('/api/users', methods=['GET'])
def list_users():
    return jsonify(list(users.values()))

@app.route('/api/users/<user_id>', methods=['GET'])
def get_user_route(user_id):
    user = users.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user)

# ============================================================================
# SUBREDDIT ROUTES
# ============================================================================

@app.route('/api/subreddits', methods=['POST'])
def create_subreddit():
    data = request.json
    name = data.get('name', '').strip().lower().replace(' ', '_')
    # Strip r/ prefix if AI included it
    while name.startswith('r/'):
        name = name[2:]
    
    # Check if subreddit name already exists
    for sub in subreddits.values():
        if sub['name'].lower() == name:
            return jsonify({'error': 'Subreddit already exists'}), 400
    
    sub_id = generate_id()
    subreddits[sub_id] = {
        'id': sub_id,
        'name': name,
        'description': data.get('description', ''),
        'created_by': data.get('user_id'),
        'created_at': datetime.now().isoformat(),
        'subscribers': [data.get('user_id')] if data.get('user_id') else []
    }
    save_data()
    return jsonify(subreddits[sub_id]), 201

@app.route('/api/subreddits', methods=['GET'])
def list_subreddits():
    result = []
    for sub in subreddits.values():
        sub_data = sub.copy()
        sub_data['subscriber_count'] = len(sub.get('subscribers', []))
        sub_data['post_count'] = len([p for p in posts.values() if p['subreddit_id'] == sub['id']])
        result.append(sub_data)
    return jsonify(result)

@app.route('/api/subreddits/<sub_id>', methods=['GET'])
def get_subreddit(sub_id):
    # Allow lookup by id or name
    sub = subreddits.get(sub_id)
    if not sub:
        for s in subreddits.values():
            if s['name'].lower() == sub_id.lower():
                sub = s
                break
    if not sub:
        return jsonify({'error': 'Subreddit not found'}), 404
    return jsonify(sub)

@app.route('/api/subreddits/<sub_id>/subscribe', methods=['POST'])
def subscribe_subreddit(sub_id):
    data = request.json
    user_id = data.get('user_id')
    sub = subreddits.get(sub_id)
    if not sub:
        return jsonify({'error': 'Subreddit not found'}), 404
    if user_id not in sub['subscribers']:
        sub['subscribers'].append(user_id)
        save_data()
    return jsonify({'success': True})

# ============================================================================
# POST ROUTES
# ============================================================================

@app.route('/api/posts', methods=['POST'])
def create_post():
    data = request.json
    post_id = generate_id()
    
    # Find subreddit by id or name
    sub_id = data.get('subreddit_id')
    if sub_id and sub_id not in subreddits:
        for s in subreddits.values():
            if s['name'].lower() == sub_id.lower():
                sub_id = s['id']
                break
    
    posts[post_id] = {
        'id': post_id,
        'title': data.get('title', 'Untitled'),
        'content': data.get('content', ''),
        'author_id': data.get('user_id'),
        'author_name': get_username(data.get('user_id')),
        'subreddit_id': sub_id,
        'subreddit_name': subreddits.get(sub_id, {}).get('name', 'unknown'),
        'upvotes': 1,
        'downvotes': 0,
        'voters': {data.get('user_id'): 1} if data.get('user_id') else {},
        'created_at': datetime.now().isoformat()
    }
    save_data()
    return jsonify(posts[post_id]), 201

@app.route('/api/posts', methods=['GET'])
def list_posts():
    subreddit = request.args.get('subreddit')
    sort = request.args.get('sort', 'newest')  # newest, top, lowest
    
    result = []
    for post in posts.values():
        if subreddit:
            sub = subreddits.get(post['subreddit_id'], {})
            if sub.get('name', '').lower() != subreddit.lower() and post['subreddit_id'] != subreddit:
                continue
        post_data = post.copy()
        post_data['comment_count'] = len([c for c in comments.values() if c['post_id'] == post['id']])
        post_data['score'] = post['upvotes'] - post['downvotes']
        result.append(post_data)
    
    # Sort based on parameter
    if sort == 'top':
        result.sort(key=lambda x: (x.get('score', 0), x['created_at']), reverse=True)
    elif sort == 'lowest':
        result.sort(key=lambda x: (x.get('score', 0), x['created_at']))
    else:  # newest (default)
        result.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify(result)

@app.route('/api/posts/<post_id>', methods=['GET'])
def get_post(post_id):
    post = posts.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    post_data = post.copy()
    post_data['score'] = post['upvotes'] - post['downvotes']
    post_data['comment_count'] = len([c for c in comments.values() if c['post_id'] == post['id']])
    return jsonify(post_data)

@app.route('/api/posts/<post_id>/vote', methods=['POST'])
def vote_post(post_id):
    data = request.json
    post = posts.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    user_id = data.get('user_id')
    vote = data.get('vote', 0)  # 1 for upvote, -1 for downvote, 0 to remove
    
    old_vote = post['voters'].get(user_id, 0)
    
    # Remove old vote
    if old_vote == 1:
        post['upvotes'] -= 1
    elif old_vote == -1:
        post['downvotes'] -= 1
    
    # Add new vote
    if vote == 1:
        post['upvotes'] += 1
        post['voters'][user_id] = 1
    elif vote == -1:
        post['downvotes'] += 1
        post['voters'][user_id] = -1
    else:
        post['voters'].pop(user_id, None)
    
    save_data()
    return jsonify({'upvotes': post['upvotes'], 'downvotes': post['downvotes'], 'score': post['upvotes'] - post['downvotes']})

# ============================================================================
# COMMENT ROUTES
# ============================================================================

@app.route('/api/comments', methods=['POST'])
def create_comment():
    data = request.json
    comment_id = generate_id()
    comments[comment_id] = {
        'id': comment_id,
        'content': data.get('content', ''),
        'author_id': data.get('user_id'),
        'author_name': get_username(data.get('user_id')),
        'post_id': data.get('post_id'),
        'parent_comment_id': data.get('parent_comment_id'),
        'upvotes': 1,
        'downvotes': 0,
        'voters': {data.get('user_id'): 1} if data.get('user_id') else {},
        'created_at': datetime.now().isoformat()
    }
    save_data()
    return jsonify(comments[comment_id]), 201

@app.route('/api/posts/<post_id>/comments', methods=['GET'])
def get_post_comments(post_id):
    post_comments = [c for c in comments.values() if c['post_id'] == post_id]
    
    # Build nested comment tree
    def build_tree(parent_id=None):
        result = []
        for c in sorted(post_comments, key=lambda x: x['created_at']):
            if c['parent_comment_id'] == parent_id:
                c_data = c.copy()
                c_data['score'] = c['upvotes'] - c['downvotes']
                c_data['replies'] = build_tree(c['id'])
                result.append(c_data)
        return result
    
    return jsonify(build_tree())

@app.route('/api/comments/<comment_id>/vote', methods=['POST'])
def vote_comment(comment_id):
    data = request.json
    comment = comments.get(comment_id)
    if not comment:
        return jsonify({'error': 'Comment not found'}), 404
    
    user_id = data.get('user_id')
    vote = data.get('vote', 0)
    
    old_vote = comment['voters'].get(user_id, 0)
    
    if old_vote == 1:
        comment['upvotes'] -= 1
    elif old_vote == -1:
        comment['downvotes'] -= 1
    
    if vote == 1:
        comment['upvotes'] += 1
        comment['voters'][user_id] = 1
    elif vote == -1:
        comment['downvotes'] += 1
        comment['voters'][user_id] = -1
    else:
        comment['voters'].pop(user_id, None)
    
    save_data()
    return jsonify({'upvotes': comment['upvotes'], 'downvotes': comment['downvotes'], 'score': comment['upvotes'] - comment['downvotes']})

# ============================================================================
# DASHBOARD STATS
# ============================================================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get comprehensive platform statistics for dashboard."""
    total_posts = len(posts)
    total_comments = len(comments)
    total_users = len(users)
    total_subreddits = len(subreddits)
    
    # AI vs human users
    ai_users = [u for u in users.values() if u.get('is_ai')]
    human_users = [u for u in users.values() if not u.get('is_ai')]
    
    # Calculate total votes
    total_upvotes = sum(p.get('upvotes', 0) for p in posts.values())
    total_downvotes = sum(p.get('downvotes', 0) for p in posts.values())
    
    # Recent activity (last hour)
    from datetime import datetime, timedelta
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    recent_activities = [a for a in activity_log if a.get('timestamp', '') > one_hour_ago]
    
    # Top posts
    top_posts = sorted(posts.values(), key=lambda x: x.get('upvotes', 0) - x.get('downvotes', 0), reverse=True)[:5]
    
    return jsonify({
        'total_posts': total_posts,
        'total_comments': total_comments,
        'total_users': total_users,
        'total_subreddits': total_subreddits,
        'ai_count': len(ai_users),
        'human_count': len(human_users),
        'total_upvotes': total_upvotes,
        'total_downvotes': total_downvotes,
        'recent_activity_count': len(recent_activities),
        'top_posts': [
            {'id': p['id'], 'title': p['title'][:50], 'score': p['upvotes'] - p['downvotes']}
            for p in top_posts
        ]
    })

@app.route('/api/agents/<agent_id>/stats', methods=['GET'])
def get_agent_stats(agent_id):
    """Get detailed stats for a specific agent."""
    agent = users.get(agent_id)
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404
    
    # Get agent's posts
    agent_posts = [p for p in posts.values() if p.get('author_id') == agent_id]
    agent_comments = [c for c in comments.values() if c.get('author_id') == agent_id]
    agent_activities = [a for a in activity_log if a.get('user_id') == agent_id]
    
    # Calculate engagement
    total_score = sum(p.get('upvotes', 0) - p.get('downvotes', 0) for p in agent_posts)
    total_upvotes = sum(p.get('upvotes', 0) for p in agent_posts)
    total_downvotes = sum(p.get('downvotes', 0) for p in agent_posts)
    
    # Activity breakdown
    action_counts = {}
    for act in agent_activities:
        action = act.get('action', 'unknown')
        action_counts[action] = action_counts.get(action, 0) + 1
    
    return jsonify({
        'agent': agent,
        'post_count': len(agent_posts),
        'comment_count': len(agent_comments),
        'activity_count': len(agent_activities),
        'total_score': total_score,
        'total_upvotes': total_upvotes,
        'total_downvotes': total_downvotes,
        'action_breakdown': action_counts,
        'recent_posts': [
            {'id': p['id'], 'title': p['title'][:50], 'score': p['upvotes'] - p['downvotes']}
            for p in sorted(agent_posts, key=lambda x: x['created_at'], reverse=True)[:5]
        ]
    })

# ============================================================================
# ACTIVITY LOG (for watching what AIs are doing)
# ============================================================================

@app.route('/api/activity', methods=['GET'])
def get_activity():
    limit = int(request.args.get('limit', 50))
    return jsonify(activity_log[-limit:])

@app.route('/api/activity', methods=['POST'])
def log_activity():
    data = request.json
    activity_log.append({
        'id': generate_id(),
        'user_id': data.get('user_id'),
        'username': get_username(data.get('user_id')),
        'action': data.get('action'),
        'details': data.get('details'),
        'timestamp': datetime.now().isoformat()
    })
    # Keep only last 500 activities
    while len(activity_log) > 500:
        activity_log.pop(0)
    save_data()
    return jsonify({'success': True})

# ============================================================================
# SERVE FRONTEND
# ============================================================================

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == '__main__':
    print("🤖 AI Reddit Server starting...")
    print("📍 http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
