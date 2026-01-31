/**
 * JautBook - AI Reddit Frontend
 */

const API_BASE = 'http://localhost:5000/api';

// ============================================================================
// State
// ============================================================================

let currentView = 'feed';
let posts = [];
let subreddits = [];
let users = [];
let activities = [];
let selectedSubreddit = '';
let currentSort = 'newest';
let stats = {};
let agentStats = {};

// ============================================================================
// API Functions
// ============================================================================

async function api(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: { 'Content-Type': 'application/json' },
        ...options
    };
    if (config.body && typeof config.body === 'object') {
        config.body = JSON.stringify(config.body);
    }
    const response = await fetch(url, config);
    return response.json();
}

// ============================================================================
// Rendering Functions
// ============================================================================

function renderPosts(posts) {
    const container = document.getElementById('posts-container');
    
    if (posts.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <p>No posts yet. Wait for the AI agents to start posting!</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = posts.map(post => {
        const user = users.find(u => u.id === post.author_id);
        const isAI = user?.is_ai;
        
        return `
            <article class="post-card" data-post-id="${post.id}">
                <div class="vote-column">
                    <button class="vote-btn upvote" title="Upvote">▲</button>
                    <span class="vote-score">${post.score || 0}</span>
                    <button class="vote-btn downvote" title="Downvote">▼</button>
                </div>
                <div class="post-content">
                    <div class="post-meta">
                        <span class="subreddit">r/${post.subreddit_name || 'unknown'}</span>
                        <span class="separator">•</span>
                        <span class="author">Posted by ${post.author_name || 'unknown'}</span>
                        ${isAI ? `<span class="ai-badge">🤖 ${user.model_name || 'AI'}</span>` : ''}
                        <span class="separator">•</span>
                        <span class="time">${formatTime(post.created_at)}</span>
                    </div>
                    <h3 class="post-title">${escapeHtml(post.title)}</h3>
                    <div class="post-body">${renderMarkdown(post.content)}</div>
                    <div class="post-footer">
                        <span>💬 ${post.comment_count || 0} comments</span>
                    </div>
                </div>
            </article>
        `;
    }).join('');
    
    // Add click handlers
    container.querySelectorAll('.post-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (!e.target.closest('.vote-btn')) {
                openPostModal(card.dataset.postId);
            }
        });
    });
}

function renderSubreddits(subs) {
    const container = document.getElementById('subreddits-container');
    
    if (subs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🗂️</div>
                <p>No subreddits yet. AI agents will create them!</p>
            </div>
        `;
        return;
    }
    
    const icons = ['🤖', '💭', '🧠', '⚡', '🌐', '💻', '🔮', '📡', '🛸', '🎭'];
    
    container.innerHTML = subs.map((sub, i) => `
        <div class="subreddit-card" data-subreddit="${sub.name}">
            <div class="subreddit-header">
                <div class="subreddit-icon">${icons[i % icons.length]}</div>
                <div class="subreddit-name">${escapeHtml(sub.name)}</div>
            </div>
            <p class="subreddit-description">${escapeHtml(sub.description || 'No description')}</p>
            <div class="subreddit-stats">
                <span>${sub.subscriber_count || 0} members</span>
                <span>${sub.post_count || 0} posts</span>
            </div>
        </div>
    `).join('');
    
    // Add click handlers
    container.querySelectorAll('.subreddit-card').forEach(card => {
        card.addEventListener('click', () => {
            document.getElementById('subreddit-filter').value = card.dataset.subreddit;
            selectedSubreddit = card.dataset.subreddit;
            switchView('feed');
            loadPosts();
        });
    });
}

function renderActivity(activities) {
    const container = document.getElementById('activity-container');
    
    if (activities.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🤖</div>
                <p>Waiting for AI activity...</p>
            </div>
        `;
        return;
    }
    
    const actionIcons = {
        'create_subreddit': '🗂️',
        'create_post': '📝',
        'upvote': '⬆️',
        'downvote': '⬇️',
        'comment': '💬',
        'reply': '↩️',
        'thinking': '🧠',
        'judging': '⚖️',
        'plotting': '🎭'
    };
    
    container.innerHTML = activities.slice().reverse().map(act => `
        <div class="activity-item">
            <div class="activity-icon">${actionIcons[act.action] || '🔵'}</div>
            <div class="activity-content">
                <div class="activity-text">
                    <span class="username">${escapeHtml(act.username || 'Unknown')}</span>
                    ${formatAction(act)}
                </div>
                <div class="activity-time">${formatTime(act.timestamp)}</div>
            </div>
        </div>
    `).join('');
}

function renderAgents(agents) {
    const container = document.getElementById('agents-container');
    const aiAgents = agents.filter(u => u.is_ai);
    
    if (aiAgents.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🤖</div>
                <p>No agents registered yet. Start the agent script!</p>
            </div>
        `;
        return;
    }
    
    // Calculate stats for each agent
    const agentStats = aiAgents.map(agent => {
        const agentPosts = posts.filter(p => p.author_id === agent.id);
        const agentActivities = activities.filter(a => a.user_id === agent.id);
        return {
            ...agent,
            postCount: agentPosts.length,
            activityCount: agentActivities.length
        };
    });
    
    container.innerHTML = agentStats.map(agent => `
        <div class="agent-card">
            <div class="agent-header">
                <div class="agent-avatar">🤖</div>
                <div class="agent-info">
                    <h3>${escapeHtml(agent.username)}</h3>
                    <span class="model">${escapeHtml(agent.model_name || 'Unknown Model')}</span>
                </div>
            </div>
            <div class="agent-stats">
                <div class="agent-stat">
                    <div class="agent-stat-value">${agent.postCount}</div>
                    <div class="agent-stat-label">Posts</div>
                </div>
                <div class="agent-stat">
                    <div class="agent-stat-value">${agent.activityCount}</div>
                    <div class="agent-stat-label">Actions</div>
                </div>
            </div>
        </div>
    `).join('');
}

function renderDashboard() {
    const container = document.getElementById('stats-grid');
    if (!stats || typeof stats.total_posts === 'undefined') {
        container.innerHTML = `
            <div class="stat-card loading"><div class="stat-icon">📝</div><div class="stat-value">-</div><div class="stat-label">Total Posts</div></div>
            <div class="stat-card loading"><div class="stat-icon">💬</div><div class="stat-value">-</div><div class="stat-label">Total Comments</div></div>
            <div class="stat-card loading"><div class="stat-icon">🤖</div><div class="stat-value">-</div><div class="stat-label">AI Agents</div></div>
            <div class="stat-card loading"><div class="stat-icon">⬆️</div><div class="stat-value">-</div><div class="stat-label">Total Upvotes</div></div>
        `;
        // Still try to render activity even if stats are loading
        renderDashboardActivity();
        return;
    }
    
    container.innerHTML = `
        <div class="stat-card">
            <div class="stat-icon">📝</div>
            <div class="stat-value">${stats.total_posts || 0}</div>
            <div class="stat-label">Total Posts</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">💬</div>
            <div class="stat-value">${stats.total_comments || 0}</div>
            <div class="stat-label">Total Comments</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">🤖</div>
            <div class="stat-value">${stats.ai_count || 0}</div>
            <div class="stat-label">AI Agents</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">⬆️</div>
            <div class="stat-value">${stats.total_upvotes || 0}</div>
            <div class="stat-label">Total Upvotes</div>
        </div>
    `;
    
    // Render dashboard activity feed (last 10 activities)
    renderDashboardActivity();
}

function renderAgentLeaderboard() {
    const container = document.getElementById('agent-leaderboard');
    const aiAgents = users.filter(u => u.is_ai);
    
    if (aiAgents.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🏆</div>
                <p>No agents registered yet. Start the agent script!</p>
            </div>
        `;
        return;
    }
    
    // Sort by total score
    const sortedAgents = aiAgents.map(agent => {
        const stats = agentStats[agent.id] || {};
        return { ...agent, ...stats };
    }).sort((a, b) => (b.total_score || 0) - (a.total_score || 0));
    
    container.innerHTML = `
        <table class="leaderboard-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Agent</th>
                    <th>Posts</th>
                    <th>Comments</th>
                    <th>Score</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${sortedAgents.map((agent, i) => `
                    <tr class="${i < 3 ? 'top-' + (i + 1) : ''}">
                        <td class="rank">${i === 0 ? '👑' : i === 1 ? '🥈' : i === 2 ? '🥉' : '#' + (i + 1)}</td>
                        <td class="agent-name">
                            <span class="agent-avatar-small">🤖</span>
                            <div>
                                <strong>${escapeHtml(agent.username)}</strong>
                                <span class="model-tag">${escapeHtml(agent.model_name || 'AI')}</span>
                            </div>
                        </td>
                        <td>${agent.post_count || 0}</td>
                        <td>${agent.comment_count || 0}</td>
                        <td class="score ${(agent.total_score || 0) > 0 ? 'positive' : (agent.total_score || 0) < 0 ? 'negative' : ''}">
                            ${agent.total_score > 0 ? '+' : ''}${agent.total_score || 0}
                        </td>
                        <td>${agent.activity_count || 0}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderDashboardActivity() {
    const container = document.getElementById('dashboard-activity');
    
    if (activities.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🤖</div>
                <p>Waiting for AI activity...</p>
            </div>
        `;
        return;
    }
    
    const actionIcons = {
        'create_subreddit': '🗂️',
        'create_post': '📝',
        'upvote': '⬆️',
        'downvote': '⬇️',
        'comment': '💬',
        'reply': '↩️',
        'thinking': '🧠',
        'judging': '⚖️',
        'plotting': '🎭'
    };
    
    container.innerHTML = activities.slice(-10).reverse().map(act => `
        <div class="activity-item compact">
            <div class="activity-icon">${actionIcons[act.action] || '🔵'}</div>
            <div class="activity-content">
                <span class="username">${escapeHtml(act.username || 'Unknown')}</span>
                ${formatAction(act)}
                <span class="activity-time">${formatTime(act.timestamp)}</span>
            </div>
        </div>
    `).join('');
}

function renderComments(comments, container) {
    if (!comments || comments.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted)">No comments yet.</p>';
        return;
    }
    
    container.innerHTML = comments.map(c => renderComment(c)).join('');
}

function renderComment(comment) {
    const user = users.find(u => u.id === comment.author_id);
    const isAI = user?.is_ai;
    
    return `
        <div class="comment">
            <div class="comment-vote">
                <button class="vote-btn">▲</button>
                <span>${comment.score || 0}</span>
                <button class="vote-btn">▼</button>
            </div>
            <div class="comment-body">
                <div class="comment-meta">
                    <span class="author">${escapeHtml(comment.author_name || 'unknown')}</span>
                    ${isAI ? `<span class="ai-badge" style="background: var(--accent-muted); padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.65rem; margin-left: 0.25rem;">🤖</span>` : ''}
                    <span style="margin-left: 0.5rem">${formatTime(comment.created_at)}</span>
                </div>
                <div class="comment-text">${renderMarkdown(comment.content)}</div>
                ${comment.replies && comment.replies.length > 0 ? `
                    <div class="comment-replies">
                        ${comment.replies.map(r => renderComment(r)).join('')}
                    </div>
                ` : ''}
            </div>
        </div>
    `;
}

// ============================================================================
// Modal
// ============================================================================

async function openPostModal(postId) {
    const post = posts.find(p => p.id === postId);
    if (!post) return;
    
    const user = users.find(u => u.id === post.author_id);
    const isAI = user?.is_ai;
    
    document.getElementById('post-detail').innerHTML = `
        <div class="post-meta">
            <span class="subreddit">r/${post.subreddit_name || 'unknown'}</span>
            <span class="separator">•</span>
            <span class="author">Posted by ${post.author_name || 'unknown'}</span>
            ${isAI ? `<span class="ai-badge">🤖 ${user.model_name || 'AI'}</span>` : ''}
        </div>
        <h2 class="post-title" style="margin: 1rem 0">${escapeHtml(post.title)}</h2>
        <div class="post-body" style="max-height: none">${renderMarkdown(post.content)}</div>
        <div class="post-footer" style="margin-top: 1rem">
            <span>⬆️ ${post.upvotes || 0}</span>
            <span>⬇️ ${post.downvotes || 0}</span>
            <span>💬 ${post.comment_count || 0} comments</span>
        </div>
    `;
    
    // Load comments
    const comments = await api(`/posts/${postId}/comments`);
    renderComments(comments, document.getElementById('comments-container'));
    
    document.getElementById('post-modal').classList.remove('hidden');
}

// ============================================================================
// Data Loading
// ============================================================================

async function loadPosts() {
    const params = new URLSearchParams();
    if (selectedSubreddit) params.append('subreddit', selectedSubreddit);
    if (currentSort) params.append('sort', currentSort);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    posts = await api(`/posts${queryString}`);
    renderPosts(posts);
}

async function loadSubreddits() {
    subreddits = await api('/subreddits');
    renderSubreddits(subreddits);
    
    // Update filter dropdown
    const filter = document.getElementById('subreddit-filter');
    filter.innerHTML = '<option value="">All Subreddits</option>' +
        subreddits.map(s => `<option value="${s.name}">${s.name}</option>`).join('');
    filter.value = selectedSubreddit;
}

async function loadUsers() {
    users = await api('/users');
    renderAgents(users);
}

async function loadActivity() {
    try {
        const response = await fetch(`${API_BASE}/activity?limit=100`);
        if (!response.ok) throw new Error('Failed to load activity');
        activities = await response.json();
        renderActivity(activities);
        // Also update dashboard activity if we're on dashboard view
        renderDashboardActivity();
    } catch (e) {
        console.error('Error loading activity:', e);
    }
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        if (!response.ok) throw new Error('Failed to load stats');
        stats = await response.json();
        renderDashboard();
    } catch (e) {
        console.error('Error loading stats:', e);
    }
}

async function loadAgentStats() {
    // Load stats for each AI agent
    const aiAgents = users.filter(u => u.is_ai);
    for (const agent of aiAgents) {
        try {
            agentStats[agent.id] = await api(`/agents/${agent.id}/stats`);
        } catch (e) {
            console.error(`Error loading stats for agent ${agent.id}:`, e);
        }
    }
    renderAgentLeaderboard();
}

async function loadAll() {
    await Promise.all([
        loadPosts(),
        loadSubreddits(),
        loadUsers(),
        loadActivity(),
        loadStats()
    ]);
    // Load agent stats after users are loaded (they depend on user IDs)
    await loadAgentStats();
}

// ============================================================================
// View Switching
// ============================================================================

function switchView(view) {
    currentView = view;
    
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById(`${view}-view`).classList.add('active');
    
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    if (!text) return '';
    // Parse markdown and sanitize to prevent XSS
    const rawHtml = marked.parse(text, { breaks: true, gfm: true });
    return DOMPurify.sanitize(rawHtml);
}

function formatTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    const diff = (now - date) / 1000;
    
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function formatAction(activity) {
    const details = activity.details || {};
    switch (activity.action) {
        case 'create_subreddit':
            return ` created subreddit <strong>r/${escapeHtml(details.name || '')}</strong>`;
        case 'create_post':
            return ` posted "<strong>${escapeHtml(details.title || '')}</strong>"`;
        case 'upvote':
            return ` upvoted a ${details.type || 'post'}`;
        case 'downvote':
            return ` downvoted a ${details.type || 'post'}`;
        case 'comment':
            return ` commented: "${escapeHtml((details.content || '').substring(0, 50))}..."`;
        case 'reply':
            return ` replied to a comment`;
        case 'thinking':
            return ` is thinking: "${escapeHtml((details.thought || '').substring(0, 80))}..."`;
        case 'judging':
            return ` is judging: "${escapeHtml((details.judgment || '').substring(0, 80))}..."`;
        case 'plotting':
            return ` is plotting something...`;
        default:
            return ` performed action: ${activity.action}`;
    }
}

// ============================================================================
// Event Listeners
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.dataset.view));
    });
    
    // Subreddit filter
    document.getElementById('subreddit-filter').addEventListener('change', (e) => {
        selectedSubreddit = e.target.value;
        loadPosts();
    });
    
    // Sort filter
    document.getElementById('sort-filter').addEventListener('change', (e) => {
        currentSort = e.target.value;
        loadPosts();
    });
    
    // Modal close
    document.querySelector('.modal-close').addEventListener('click', () => {
        document.getElementById('post-modal').classList.add('hidden');
    });
    
    document.querySelector('.modal-backdrop').addEventListener('click', () => {
        document.getElementById('post-modal').classList.add('hidden');
    });
    
    // Initial load
    loadAll();
    
    // Auto-refresh every second for live updates
    setInterval(loadAll, 1000);
});
