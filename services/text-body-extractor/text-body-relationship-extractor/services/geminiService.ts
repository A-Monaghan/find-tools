
import { GoogleGenAI, Type } from "@google/genai";
import { RawEntity, RawRelationship } from "../types";

const responseSchema = {
  type: Type.OBJECT,
  properties: {
    entities: {
      type: Type.ARRAY,
      description: "A list of all unique entities found in the text.",
      items: {
        type: Type.OBJECT,
        properties: {
          name: {
            type: Type.STRING,
            description: "The unique name of the entity (e.g., 'John Doe', 'Acme Corp').",
          },
          label: {
            type: Type.STRING,
            description: "A concise category label for the entity (e.g., 'Person', 'Company', 'Location').",
          },
        },
        required: ["name", "label"],
      },
    },
    relationships: {
      type: Type.ARRAY,
      description: "A list of all relationships connecting the entities.",
      items: {
        type: Type.OBJECT,
        properties: {
          source: {
            type: Type.STRING,
            description: "The name of the source entity. Must match a name in the entities list.",
          },
          target: {
            type: Type.STRING,
            description: "The name of the target entity. Must match a name in the entities list.",
          },
          type: {
            type: Type.STRING,
            description: "The type of relationship in uppercase_snake_case format (e.g., 'WORKS_FOR', 'LOCATED_IN').",
          },
        },
        required: ["source", "target", "type"],
      },
    },
  },
  required: ["entities", "relationships"],
};

export const getTextFromUrl = async (url: string, apiKey: string): Promise<string> => {
  if (!apiKey) {
    throw new Error("API key is required to fetch from URL.");
  }
  const ai = new GoogleGenAI({ apiKey });

  const systemInstruction = `You are an expert web content extractor. Your primary task is to extract the main article text from the given URL. 
Return ONLY the raw text content of the article body. 
You must exclude all non-content elements such as navigation bars, headers, footers, advertisements, sidebars, and comment sections. 
Do not provide any summary, commentary, preamble, or any text other than the article's main body itself.`;
  
  try {
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: `Please extract the text content from this URL: ${url}`,
      config: {
        systemInstruction,
        tools: [{googleSearch: {}}],
      },
    });

    // #region agent log
    const hasText = typeof (response as any).text !== 'undefined';
    fetch('http://127.0.0.1:7247/ingest/7e6b97fd-5f69-4e37-adee-b00120ba6a9b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'geminiService.ts:getTextFromUrl',message:'response shape',data:{hasText,responseKeys: response ? Object.keys(response as object) : []},timestamp:Date.now(),hypothesisId:'H5'})}).catch(()=>{});
    // #endregion
    const text = response.text;
    if (!text || text.trim().length === 0) {
        throw new Error("Extracted text is empty. The URL might not contain a readable article or is inaccessible.");
    }
    return text;
  } catch (error) {
    // #region agent log
    fetch('http://127.0.0.1:7247/ingest/7e6b97fd-5f69-4e37-adee-b00120ba6a9b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'geminiService.ts:getTextFromUrl',message:'catch',data:{error: String((error as Error).message)},timestamp:Date.now(),hypothesisId:'H5'})}).catch(()=>{});
    // #endregion
    console.error("Error fetching content from URL with Gemini:", error);
    throw new Error("Failed to fetch content from the URL. The URL might be inaccessible, or the content could not be processed.");
  }
};

export const extractGraphData = async (text: string, apiKey: string): Promise<{ entities: RawEntity[]; relationships: RawRelationship[] }> => {
  if (!apiKey) {
    throw new Error("API key is required to extract graph data.");
  }
  const ai = new GoogleGenAI({ apiKey });
  
  const systemInstruction = `You are an expert data analyst specializing in knowledge graph extraction. 
Your task is to analyze the given text and identify all distinct entities and the relationships between them.
Entities should be people, organizations, locations, concepts, or significant items. Assign a concise, descriptive label for each entity (e.g., 'Person', 'Company', 'City').
Relationships should describe how two entities are connected (e.g., 'WORKS_FOR', 'LOCATED_IN', 'CEO_OF').
The 'source' and 'target' in a relationship must exactly match an entity 'name'.
Format the output strictly as a JSON object according to the provided schema. Do not add any explanatory text or markdown formatting.`;

  try {
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: `Analyze the following text and extract entities and their relationships:\n\n---\n${text}\n---`,
      config: {
        systemInstruction,
        responseMimeType: "application/json",
        responseSchema: responseSchema,
      },
    });

    // #region agent log
    fetch('http://127.0.0.1:7247/ingest/7e6b97fd-5f69-4e37-adee-b00120ba6a9b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'geminiService.ts:extractGraphData',message:'response before text',data:{hasText: typeof (response as any).text !== 'undefined',responseKeys: response ? Object.keys(response as object) : []},timestamp:Date.now(),hypothesisId:'H5'})}).catch(()=>{});
    // #endregion
    const jsonText = response.text.trim();
    const parsedData = JSON.parse(jsonText);

    return {
      entities: parsedData.entities || [],
      relationships: parsedData.relationships || [],
    };
  } catch (error) {
    // #region agent log
    fetch('http://127.0.0.1:7247/ingest/7e6b97fd-5f69-4e37-adee-b00120ba6a9b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'geminiService.ts:extractGraphData',message:'catch',data:{error: String((error as Error).message)},timestamp:Date.now(),hypothesisId:'H5'})}).catch(()=>{});
    // #endregion
    console.error("Error calling Gemini API:", error);
    throw new Error("Failed to process text with Gemini API.");
  }
};
