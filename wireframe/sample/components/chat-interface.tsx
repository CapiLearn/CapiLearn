"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Send, Sparkles, Sprout } from "lucide-react"
import { Message } from "@/components/chat-dashboard"
import { useState, useRef, useEffect } from "react"

interface ChatInterfaceProps {
  messages: Message[]
  onSendMessage: (content: string) => void
}

export function ChatInterface({ messages, onSendMessage }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState("")
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (inputValue.trim()) {
      onSendMessage(inputValue.trim())
      setInputValue("")
    }
  }

  const suggestedTopics = [
    "Help me understand calculus derivatives",
    "Explain photosynthesis in simple terms",
    "Quiz me on world history",
    "What are Newton's laws of motion?",
  ]

  return (
    <div className="flex flex-1 flex-col bg-background">
      {/* Chat Header */}
      <div className="flex h-16 items-center border-b border-border px-6">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h1 className="font-semibold text-foreground">AI Tutor</h1>
        </div>
      </div>

      {/* Messages Area */}
      <ScrollArea ref={scrollAreaRef} className="flex-1 px-6">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center py-16">
            <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
              <Sprout className="h-8 w-8 text-primary" />
            </div>
            <h2 className="mb-2 text-xl font-semibold text-foreground">
              What would you like to learn today?
            </h2>
            <p className="mb-8 max-w-md text-center text-muted-foreground">
              Ask CapiLearn anything about your studies. I can help with math, science, history, languages, and more.
            </p>
            <div className="grid w-full max-w-2xl gap-3 sm:grid-cols-2">
              {suggestedTopics.map((topic, index) => (
                <button
                  key={index}
                  onClick={() => onSendMessage(topic)}
                  className="rounded-xl border border-border bg-card p-4 text-left text-sm text-foreground transition-colors hover:border-accent hover:bg-secondary"
                >
                  {topic}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6 py-6">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-4 ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                {message.role === "assistant" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary">
                    <Sprout className="h-5 w-5 text-primary-foreground" />
                  </div>
                )}
                <div
                  className={`max-w-2xl rounded-2xl px-4 py-3 shadow-sm ${
                    message.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "border border-border bg-card text-card-foreground"
                  }`}
                >
                  <div className="whitespace-pre-wrap text-sm leading-relaxed">
                    {message.content}
                  </div>
                </div>
                {message.role === "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-medium text-accent-foreground">
                    S
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </ScrollArea>

      {/* Input Area */}
      <div className="border-t border-border p-6">
        <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
          <div className="flex gap-3">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask me anything..."
              className="flex-1 bg-card text-foreground placeholder:text-muted-foreground"
            />
            <Button
              type="submit"
              disabled={!inputValue.trim()}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <Send className="h-4 w-4" />
              <span className="sr-only">Send message</span>
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            AI responses are generated and may contain errors. Always verify important information.
          </p>
        </form>
      </div>
    </div>
  )
}
