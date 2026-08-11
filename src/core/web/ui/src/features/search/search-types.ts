// Shapes served by cos_search / cos_doc_search / cos_task_search /
// cos_graph_query via routes/search.py.

export interface MemoryHit {
  id?: string | number | null;
  title?: string;
  summary?: string;
  content?: string;
  memory_type?: string;
  source_table?: string;
  confidence?: number;
  impact_score?: number;
  semantic_score?: number;
}

export interface MemoryPayload {
  results?: MemoryHit[];
  count?: number;
}

export interface DocHit {
  id?: number;
  title?: string;
  heading_path?: string;
  path?: string;
  source_path?: string;
  source_type?: string;
  snippet?: string;
  content?: string;
  score?: number;
  cosine?: number;
}

export interface DocsPayload {
  results?: DocHit[];
  count?: number;
}

export interface TaskHit {
  task_id?: string;
  title?: string;
  goal_text?: string;
  status?: string;
  domain?: string;
  file_path?: string;
  score?: number;
}

export interface TasksPayload {
  results?: TaskHit[];
  count?: number;
}

export interface GraphHit {
  uid: string;
  kind?: string;
  label?: string;
  file_path?: string;
  confidence?: number;
}

export interface GraphQueryPayload {
  results?: GraphHit[];
}

