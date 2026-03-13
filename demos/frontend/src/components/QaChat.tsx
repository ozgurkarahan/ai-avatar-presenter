import React, { useState } from 'react';
import { askQuestion, type QaResponse } from '../services/api';

interface Props {
  presentationId: string;
  slideIndex: number;
}

interface Message {
  role: 'user' | 'assistant';
  text: string;
  sourceSlides?: number[];
}

const styles: Record<string, React.CSSProperties> = {
  title: {
    fontSize: '14px',
    fontWeight: 600,
    marginBottom: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  messages: {
    maxHeight: '250px',
    overflowY: 'auto' as const,
    marginBottom: '12px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
  },
  message: {
    padding: '10px 14px',
    borderRadius: '10px',
    fontSize: '13px',
    lineHeight: 1.5,
    maxWidth: '90%',
  },
  userMsg: {
    background: '#005599',
    color: 'white',
    alignSelf: 'flex-end' as const,
    borderBottomRightRadius: '4px',
  },
  assistantMsg: {
    background: '#f0f2f5',
    color: '#333',
    alignSelf: 'flex-start' as const,
    borderBottomLeftRadius: '4px',
  },
  sourceTag: {
    fontSize: '11px',
    color: '#888',
    marginTop: '4px',
  },
  form: {
    display: 'flex',
    gap: '8px',
  },
  input: {
    flex: 1,
    padding: '8px 12px',
    border: '1px solid #ddd',
    borderRadius: '8px',
    fontSize: '13px',
    outline: 'none',
  },
  sendBtn: {
    padding: '8px 16px',
    background: '#005599',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '13px',
    cursor: 'pointer',
  },
  empty: {
    textAlign: 'center' as const,
    color: '#999',
    fontSize: '13px',
    padding: '20px 0',
  },
};

export default function QaChat({ presentationId, slideIndex }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: 'user', text: question }]);
    setInput('');
    setLoading(true);

    try {
      const res = await askQuestion(presentationId, question, slideIndex);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: res.answer,
          sourceSlides: res.source_slides,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: "Sorry, I couldn't process your question. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={styles.title}>💬 Slide Q&A</div>

      <div style={styles.messages}>
        {messages.length === 0 ? (
          <div style={styles.empty}>
            Ask a question about the current slide
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i}>
              <div
                style={{
                  ...styles.message,
                  ...(msg.role === 'user' ? styles.userMsg : styles.assistantMsg),
                }}
              >
                {msg.text}
              </div>
              {msg.sourceSlides && msg.sourceSlides.length > 0 && (
                <div style={styles.sourceTag}>
                  📎 Source: Slide{msg.sourceSlides.length > 1 ? 's' : ''}{' '}
                  {msg.sourceSlides.map((s) => s + 1).join(', ')}
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div style={{ ...styles.message, ...styles.assistantMsg }}>
            ⏳ Thinking...
          </div>
        )}
      </div>

      <form style={styles.form} onSubmit={handleSubmit}>
        <input
          style={styles.input}
          type="text"
          placeholder="Ask about this slide..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button style={styles.sendBtn} type="submit" disabled={loading}>
          Send
        </button>
      </form>
    </div>
  );
}
