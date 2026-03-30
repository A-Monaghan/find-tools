
export interface Entity {
  id: string;
  name: string;
  label: string;
}

export interface Relationship {
  id: string; // A unique ID for the relationship itself, e.g., sourceId_type_targetId
  source: string; // The ID of the source entity
  target: string; // The ID of the target entity
  type: string;
}

// Type as returned from Gemini API before processing
export interface RawEntity {
  name: string;
  label: string;
}

export interface RawRelationship {
  source: string;
  target: string;
  type: string;
}
