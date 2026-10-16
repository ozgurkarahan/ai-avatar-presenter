import React, { useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';
import { agentChat, type AgentChatMessage } from '../services/api';
import { Button, Input, Spinner } from '../ui';
import '../styles/shared/qa-chat.css';

interface Props {
  presentationId: string;
  slideIndex: number;
}

interface Message {
  role: 'user' | 'assistant';
  text: string;
}

export default function QaChat({ presentationId, slideIndex }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [history, setHistory] = useState<AgentChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, loading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: 'user', text: question }]);
    setInput('');
    setLoading(true);

    const newHistory: AgentChatMessage[] = [...history, { role: 'user', content: question }];

    try {
      const res = await agentChat(newHistory, presentationId, slideIndex);
      const reply = res.reply;
      setMessages((prev) => [...prev, { role: 'assistant', text: reply }]);
      setHistory([...newHistory, { role: 'assistant', content: reply }]);
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
    <section className="qa-chat" aria-label="Ask the presenter">
      <div className="qa-chat__head">
        <span className="eyebrow">Ask the presenter</span>
        <span className="small muted tabular">Slide {slideIndex + 1}</span>
      </div>

      <div className="qa-chat__messages" ref={listRef} aria-live="polite">
        {messages.length === 0 ? (
          <p className="qa-chat__empty">
            Ask a question about this deck, request a translation, or ask the presenter to cover a slide.
          </p>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={`qa-chat__msg qa-chat__msg--${msg.role}`}>
              <span className="sr-only">{msg.role === 'user' ? 'You:' : 'Presenter:'}</span>
              {msg.text}
            </div>
          ))
        )}
        {loading && (
          <div className="qa-chat__msg qa-chat__msg--assistant">
            <Spinner label="Thinking…" />
          </div>
        )}
      </div>

      <form className="qa-chat__form" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor={`qa-input-${presentationId}`}>Your question</label>
        <Input
          id={`qa-input-${presentationId}`}
          data-testid="qa-input"
          type="text"
          placeholder="Ask, translate, or present…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <Button type="submit" variant="primary" iconOnly icon={Send} aria-label="Send question" disabled={loading} />
      </form>
    </section>
  );
}
