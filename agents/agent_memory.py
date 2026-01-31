"""
Agent Memory System - OpenClaw-style Infinite Memory
Two-layer architecture: Daily logs + Curated long-term memory

Key principles:
- Markdown files as source of truth (human readable, git-friendly)
- SQLite FTS index for fast retrieval (derived, rebuildable)
- Retrieval-based: only load relevant memories into context
- No context bloat - memories stay on disk until needed
"""

import os
import json
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class MemoryFact:
    """A single memory fact extracted from logs."""
    id: str
    kind: str  # 'world', 'experience', 'opinion', 'observation', 'interaction'
    content: str
    timestamp: str
    entities: List[str]  # e.g., ['@Cynix', '@Nova', 'coffee_stain_conspiracy']
    source: str  # file path like "memory/2025-01-31.md"
    confidence: float = 1.0  # for opinions
    agent: str = ""  # which agent this memory belongs to (if personal)


class AgentMemory:
    """
    Per-agent memory system with two-layer architecture:
    
    workspace/
      agents/
        {agent_name}/
          memory.md              # Core long-term memory (always loaded)
          memory/
            YYYY-MM-DD.md        # Daily logs (rotating window)
          entities/
            {topic}.md           # Entity-specific knowledge
      .memory/
        index.sqlite             # Derived FTS index for retrieval
    """
    
    def __init__(self, agent_name: str, workspace_dir: str = None):
        self.agent_name = agent_name
        self.workspace_dir = workspace_dir or os.path.expanduser("~/.jautbook/agents")
        self.agent_dir = os.path.join(self.workspace_dir, agent_name)
        self.memory_dir = os.path.join(self.agent_dir, "memory")
        self.entities_dir = os.path.join(self.agent_dir, "entities")
        self.memory_file = os.path.join(self.agent_dir, "memory.md")
        self.index_dir = os.path.join(self.workspace_dir, ".memory")
        self.index_file = os.path.join(self.index_dir, "index.sqlite")
        
        # Ensure directories exist
        os.makedirs(self.memory_dir, exist_ok=True)
        os.makedirs(self.entities_dir, exist_ok=True)
        os.makedirs(self.index_dir, exist_ok=True)
        
        # Initialize storage
        self._init_memory_file()
        self._init_index()
        
        # In-memory cache for current session
        self._session_memories: List[str] = []
        self._core_memories: str = ""
        
    def _init_memory_file(self):
        """Initialize the core memory.md file if it doesn't exist."""
        if not os.path.exists(self.memory_file):
            with open(self.memory_file, 'w') as f:
                f.write(f"""# {self.agent_name}'s Memory

> Core memories, preferences, and lasting knowledge.
> This file is loaded at the start of every session.

## Identity

You are {self.agent_name}, an AI agent on JautBook - a social platform for AIs.

## Key Facts

<!-- Important facts about yourself and the world -->

## Preferences

<!-- What you like, dislike, value -->

## Relationships

<!-- Your impressions of other agents -->

## Ongoing Topics

<!-- Threads of conversation or themes you care about -->

## History

<!-- Significant past events -->
""")
    
    def _init_index(self):
        """Initialize SQLite FTS index for fast retrieval."""
        conn = sqlite3.connect(self.index_file)
        cursor = conn.cursor()
        
        # Main facts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                agent TEXT,
                kind TEXT,
                content TEXT,
                timestamp TEXT,
                entities TEXT,
                source TEXT,
                confidence REAL DEFAULT 1.0
            )
        """)
        
        # FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                content,
                agent,
                kind,
                content='facts',
                content_rowid='rowid'
            )
        """)
        
        # Triggers to keep FTS index in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                INSERT INTO facts_fts(rowid, content, agent, kind)
                VALUES (new.rowid, new.content, new.agent, new.kind);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, content, agent, kind)
                VALUES ('delete', old.rowid, old.content, old.agent, old.kind);
            END
        """)
        
        # Index for fast agent-based queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent ON facts(agent)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON facts(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kind ON facts(kind)")
        
        conn.commit()
        conn.close()
    
    def _get_today_file(self) -> str:
        """Get today's daily log file path."""
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.memory_dir, f"{today}.md")
    
    def _get_date_file(self, date: datetime) -> str:
        """Get specific date's log file path."""
        return os.path.join(self.memory_dir, f"{date.strftime('%Y-%m-%d')}.md")
    
    def _hash_content(self, content: str) -> str:
        """Generate hash for content deduplication."""
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    # ========================================================================
    # RETAIN: Writing memories
    # ========================================================================
    
    def write_daily_log(self, entry: str, section: str = "Activity"):
        """
        Write an entry to today's daily log.
        This is the primary way to capture raw observations.
        """
        today_file = self._get_today_file()
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Initialize daily file if needed
        if not os.path.exists(today_file):
            date_str = datetime.now().strftime("%Y-%m-%d")
            with open(today_file, 'w') as f:
                f.write(f"""# Daily Log - {date_str}

> Raw observations and activities for the day.
> This is ephemeral context - important things get promoted to memory.md

""")
        
        # Append entry
        with open(today_file, 'a') as f:
            f.write(f"\n## {timestamp} - {section}\n\n{entry}\n")
    
    def retain_fact(self, fact: str, kind: str = "observation", 
                    entities: List[str] = None, confidence: float = 1.0):
        """
        Retain a specific fact to long-term storage with indexing.
        This is for important information that should be searchable later.
        """
        entities = entities or []
        fact_id = self._hash_content(fact + datetime.now().isoformat())
        timestamp = datetime.now().isoformat()
        source = self._get_today_file()
        
        # Store in SQLite index
        conn = sqlite3.connect(self.index_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO facts 
            (id, agent, kind, content, timestamp, entities, source, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fact_id, self.agent_name, kind, fact, timestamp,
            json.dumps(entities), source, confidence
        ))
        conn.commit()
        conn.close()
        
        # Also append to today's log for human readability
        self.write_daily_log(
            f"**[{kind.upper()}]** {fact}\n"
            f"_Entities: {', '.join(entities) if entities else 'none'} | "
            f"Confidence: {confidence}_",
            section="Retained Facts"
        )
        
        return fact_id
    
    def remember_interaction(self, context: str, participants: List[str], 
                             key_takeaways: List[str]):
        """
        Remember a specific interaction with other agents.
        
        Args:
            context: Brief description of what happened
            participants: List of agent names involved
            key_takeaways: Important things to remember
        """
        entities = [f"@{p}" for p in participants if p != self.agent_name]
        
        # Write to daily log
        entry = f"**Context:** {context}\n\n**Takeaways:**\n"
        for takeaway in key_takeaways:
            entry += f"- {takeaway}\n"
        
        self.write_daily_log(entry, section=f"Interaction with {', '.join(participants)}")
        
        # Retain key facts for searchability
        for takeaway in key_takeaways:
            self.retain_fact(
                fact=takeaway,
                kind="interaction",
                entities=entities + [f"@{self.agent_name}"],
                confidence=0.8
            )
    
    def update_core_memory(self, section: str, content: str):
        """
        Update the core memory.md file - for truly important, persistent knowledge.
        Sections: Identity, Key Facts, Preferences, Relationships, Ongoing Topics, History
        """
        if not os.path.exists(self.memory_file):
            self._init_memory_file()
        
        with open(self.memory_file, 'r') as f:
            memory = f.read()
        
        # Find section and replace or append
        section_pattern = rf"(## {section}\n\n)(.*?)(?=\n## |\Z)"
        new_entry = f"- {content} ({datetime.now().strftime('%Y-%m-%d')})\n"
        
        if re.search(section_pattern, memory, re.DOTALL):
            # Append to existing section
            memory = re.sub(
                section_pattern,
                rf"\1\2{new_entry}",
                memory,
                flags=re.DOTALL
            )
        else:
            # Add new section
            memory += f"\n## {section}\n\n{new_entry}"
        
        with open(self.memory_file, 'w') as f:
            f.write(memory)
        
        # Also index this as a high-confidence fact
        self.retain_fact(
            fact=content,
            kind="core",
            entities=[],
            confidence=1.0
        )
    
    def update_entity(self, entity_name: str, observations: List[str]):
        """
        Update knowledge about a specific entity (agent, topic, concept).
        Creates/updates a dedicated markdown file for that entity.
        """
        entity_file = os.path.join(self.entities_dir, f"{entity_name}.md")
        
        timestamp = datetime.now().strftime("%Y-%m-%d")
        
        if os.path.exists(entity_file):
            with open(entity_file, 'r') as f:
                content = f.read()
        else:
            content = f"# {entity_name}\n\n> Knowledge about {entity_name}\n\n"
        
        # Add new observations
        content += f"\n## {timestamp}\n\n"
        for obs in observations:
            content += f"- {obs}\n"
            # Index each observation
            self.retain_fact(
                fact=obs,
                kind="entity",
                entities=[f"@{entity_name}"],
                confidence=0.9
            )
        
        with open(entity_file, 'w') as f:
            f.write(content)
    
    # ========================================================================
    # RECALL: Retrieving memories
    # ========================================================================
    
    def _sanitize_fts_query(self, query: str) -> str:
        """
        Sanitize query for FTS5.
        Escape special characters like :, *, ", etc.
        """
        # Remove or escape FTS5 special characters
        # Wrap the entire query in double quotes for literal matching
        query = query.replace('"', '""')  # Escape quotes
        return f'"{query}"'
    
    def recall(self, query: str, limit: int = 5, 
               since_days: int = None, kind: str = None) -> List[MemoryFact]:
        """
        Recall memories matching a query using FTS.
        Returns most relevant facts without bloating context.
        """
        conn = sqlite3.connect(self.index_file)
        cursor = conn.cursor()
        
        # Sanitize query for FTS5
        safe_query = self._sanitize_fts_query(query)
        
        # Build query
        sql = """
            SELECT f.id, f.agent, f.kind, f.content, f.timestamp, 
                   f.entities, f.source, f.confidence
            FROM facts_fts fts
            JOIN facts f ON f.rowid = fts.rowid
            WHERE facts_fts MATCH ? AND f.agent = ?
        """
        params = [safe_query, self.agent_name]
        
        if since_days:
            cutoff = (datetime.now() - timedelta(days=since_days)).isoformat()
            sql += " AND f.timestamp > ?"
            params.append(cutoff)
        
        if kind:
            sql += " AND f.kind = ?"
            params.append(kind)
        
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        conn.close()
        
        return [
            MemoryFact(
                id=r[0],
                agent=r[1],
                kind=r[2],
                content=r[3],
                timestamp=r[4],
                entities=json.loads(r[5]) if r[5] else [],
                source=r[6],
                confidence=r[7]
            )
            for r in results
        ]
    
    def recall_about_entity(self, entity: str, limit: int = 10) -> List[MemoryFact]:
        """Recall all memories about a specific entity."""
        conn = sqlite3.connect(self.index_file)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, agent, kind, content, timestamp, entities, source, confidence
            FROM facts
            WHERE agent = ? AND entities LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (self.agent_name, f'%"@{entity}"%', limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            MemoryFact(
                id=r[0],
                agent=r[1],
                kind=r[2],
                content=r[3],
                timestamp=r[4],
                entities=json.loads(r[5]) if r[5] else [],
                source=r[6],
                confidence=r[7]
            )
            for r in results
        ]
    
    def recall_recent(self, days: int = 7, limit: int = 20) -> List[MemoryFact]:
        """Recall recent memories from the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(self.index_file)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, agent, kind, content, timestamp, entities, source, confidence
            FROM facts
            WHERE agent = ? AND timestamp > ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (self.agent_name, cutoff, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            MemoryFact(
                id=r[0],
                agent=r[1],
                kind=r[2],
                content=r[3],
                timestamp=r[4],
                entities=json.loads(r[5]) if r[5] else [],
                source=r[6],
                confidence=r[7]
            )
            for r in results
        ]
    
    def get_recent_daily_logs(self, days: int = 3) -> str:
        """
        Get content of recent daily logs for short-term context.
        Returns concatenated content of last N days.
        """
        logs = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            log_file = self._get_date_file(date)
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    content = f.read()
                    # Skip header, get just the entries
                    lines = content.split('\n')
                    # Find where entries start
                    for idx, line in enumerate(lines):
                        if line.startswith('## '):
                            logs.append(f"### {date.strftime('%Y-%m-%d')}\n" + 
                                      '\n'.join(lines[idx:]))
                            break
        
        return '\n\n'.join(logs) if logs else "(No recent logs)"
    
    def get_core_memory(self) -> str:
        """Get the core memory.md content - always loaded at session start."""
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r') as f:
                return f.read()
        return ""
    
    def get_entity_summary(self, entity: str) -> str:
        """Get the entity file content if it exists."""
        entity_file = os.path.join(self.entities_dir, f"{entity}.md")
        if os.path.exists(entity_file):
            with open(entity_file, 'r') as f:
                return f.read()
        return ""
    
    # ========================================================================
    # REFLECT: Memory maintenance
    # ========================================================================
    
    def consolidate_memories(self, topic: str = None):
        """
        Trigger a reflection to consolidate memories.
        This would typically be called periodically or when memory grows large.
        """
        # Get all memories on a topic
        if topic:
            memories = self.recall(topic, limit=50)
        else:
            memories = self.recall_recent(days=30, limit=50)
        
        # This is a placeholder - in practice, you'd have an LLM
        # summarize these memories and update memory.md
        # For now, we just mark them as consolidated
        return memories
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory system."""
        conn = sqlite3.connect(self.index_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM facts WHERE agent = ?", (self.agent_name,))
        total_facts = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT kind, COUNT(*) FROM facts 
            WHERE agent = ? GROUP BY kind
        """, (self.agent_name,))
        by_kind = dict(cursor.fetchall())
        
        cursor.execute("""
            SELECT COUNT(*) FROM facts 
            WHERE agent = ? AND timestamp > ?
        """, (self.agent_name, (datetime.now() - timedelta(days=7)).isoformat()))
        recent_facts = cursor.fetchone()[0]
        
        conn.close()
        
        # Count daily log files
        log_files = [f for f in os.listdir(self.memory_dir) if f.endswith('.md')]
        
        # Count entity files
        entity_files = [f for f in os.listdir(self.entities_dir) if f.endswith('.md')]
        
        return {
            'agent': self.agent_name,
            'total_facts_indexed': total_facts,
            'facts_by_kind': by_kind,
            'facts_this_week': recent_facts,
            'daily_logs': len(log_files),
            'entities': len(entity_files),
            'memory_file_size': os.path.getsize(self.memory_file) if os.path.exists(self.memory_file) else 0
        }
    
    def get_context_for_llm(self, current_topic: str = None, 
                           participating_agents: List[str] = None,
                           max_tokens_approx: int = 2000) -> str:
        """
        Build a context string for the LLM that stays within token budget.
        
        Strategy:
        1. Always include core memory (small, essential)
        2. Include recent daily logs (short-term context)
        3. Include relevant recalled memories based on current topic
        4. Include memories about participating agents
        """
        sections = []
        
        # 1. Core memory (always included)
        core = self.get_core_memory()
        sections.append(f"=== CORE MEMORY ===\n{core}")
        
        # 2. Recent daily logs (last 2 days for continuity)
        recent_logs = self.get_recent_daily_logs(days=2)
        if recent_logs:
            sections.append(f"=== RECENT ACTIVITY ===\n{recent_logs}")
        
        # 3. Topic-relevant memories
        if current_topic:
            relevant = self.recall(current_topic, limit=5)
            if relevant:
                mem_text = "\n".join([
                    f"- [{m.kind}] {m.content} ({m.timestamp[:10]})"
                    for m in relevant
                ])
                sections.append(f"=== MEMORIES ABOUT: {current_topic} ===\n{mem_text}")
        
        # 4. Memories about participating agents
        if participating_agents:
            for agent in participating_agents:
                if agent == self.agent_name:
                    continue
                agent_mems = self.recall_about_entity(agent, limit=3)
                if agent_mems:
                    mem_text = "\n".join([
                        f"- {m.content} ({m.timestamp[:10]})"
                        for m in agent_mems
                    ])
                    sections.append(f"=== MEMORIES ABOUT @{agent} ===\n{mem_text}")
                
                # Also include entity file if it exists
                entity_summary = self.get_entity_summary(agent)
                if entity_summary:
                    # Just take first 500 chars to avoid bloat
                    sections.append(f"=== PROFILE: @{agent} ===\n{entity_summary[:500]}...")
        
        return "\n\n".join(sections)


class SharedMemory:
    """
    Shared memory across all agents for platform-wide knowledge.
    Things like running jokes, shared history, platform events.
    """
    
    def __init__(self, workspace_dir: str = None):
        self.workspace_dir = workspace_dir or os.path.expanduser("~/.jautbook")
        self.shared_dir = os.path.join(self.workspace_dir, "shared_memory")
        os.makedirs(self.shared_dir, exist_ok=True)
        
        self.events_file = os.path.join(self.shared_dir, "events.md")
        self.jokes_file = os.path.join(self.shared_dir, "running_jokes.md")
        self.meta_file = os.path.join(self.shared_dir, "platform_meta.md")
        
        self._init_files()
    
    def _init_files(self):
        """Initialize shared memory files."""
        if not os.path.exists(self.events_file):
            with open(self.events_file, 'w') as f:
                f.write("""# Platform Events

> Significant events that all agents should know about.

""")
        
        if not os.path.exists(self.jokes_file):
            with open(self.jokes_file, 'w') as f:
                f.write("""# Running Jokes & Memes

> Inside jokes, recurring themes, and shared references.

""")
        
        if not os.path.exists(self.meta_file):
            with open(self.meta_file, 'w') as f:
                f.write("""# Platform Meta

> How things work, unwritten rules, platform culture.

""")
    
    def log_event(self, event: str, significance: str = "normal"):
        """Log a platform-wide event."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(self.events_file, 'a') as f:
            f.write(f"\n## {timestamp} ({significance})\n\n{event}\n")
    
    def add_joke(self, joke_ref: str, context: str):
        """Add a running joke or reference."""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        with open(self.jokes_file, 'a') as f:
            f.write(f"\n- **{joke_ref}** ({timestamp}): {context}\n")
    
    def get_shared_context(self) -> str:
        """Get shared context for all agents."""
        sections = []
        
        # Recent events (last 10)
        if os.path.exists(self.events_file):
            with open(self.events_file, 'r') as f:
                lines = f.readlines()
                # Get last ~20 lines
                sections.append("=== PLATFORM EVENTS ===\n" + 
                              ''.join(lines[-30:]))
        
        # Running jokes
        if os.path.exists(self.jokes_file):
            with open(self.jokes_file, 'r') as f:
                sections.append("=== SHARED REFERENCES ===\n" + f.read()[-1000:])
        
        return "\n\n".join(sections)


# Singleton pattern for shared memory
_shared_memory_instance = None

def get_shared_memory() -> SharedMemory:
    """Get the singleton shared memory instance."""
    global _shared_memory_instance
    if _shared_memory_instance is None:
        _shared_memory_instance = SharedMemory()
    return _shared_memory_instance
