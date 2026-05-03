"use client"

import { ConversationSidebar } from "@/components/conversation-sidebar"
import { ChatInterface } from "@/components/chat-interface"
import { StreakCalendar } from "@/components/streak-calendar"
import { useState } from "react"

interface ChatDashboardProps {
  onLogout: () => void
}

export interface Conversation {
  id: string
  title: string
  date: string
  preview: string
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
}

const sampleConversations: Conversation[] = [
  {
    id: "1",
    title: "Calculus: Derivatives",
    date: "Today",
    preview: "Can you explain the chain rule?",
  },
  {
    id: "2",
    title: "Biology: Cell Division",
    date: "Today",
    preview: "What is mitosis vs meiosis?",
  },
  {
    id: "3",
    title: "History: World War II",
    date: "Yesterday",
    preview: "Key events leading to WWII",
  },
  {
    id: "4",
    title: "Physics: Newton's Laws",
    date: "Yesterday",
    preview: "Explain the third law of motion",
  },
  {
    id: "5",
    title: "Chemistry: Periodic Table",
    date: "Last Week",
    preview: "How are elements organized?",
  },
]

export function ChatDashboard({ onLogout }: ChatDashboardProps) {
  const [conversations, setConversations] = useState<Conversation[]>(sampleConversations)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])

  const handleNewConversation = () => {
    setActiveConversationId(null)
    setMessages([])
  }

  const handleSelectConversation = (id: string) => {
    setActiveConversationId(id)
    // Simulate loading conversation messages
    const conversation = conversations.find(c => c.id === id)
    if (conversation) {
      setMessages([
        {
          id: "1",
          role: "user",
          content: conversation.preview,
          timestamp: new Date(),
        },
        {
          id: "2",
          role: "assistant",
          content: `I'd be happy to help you understand "${conversation.title.split(": ")[1] || conversation.title}". Let me break this down for you step by step.\n\nThis is a fascinating topic that many students find challenging at first. The key concepts you need to understand are:\n\n1. **Core Principles** - Understanding the fundamental building blocks\n2. **Applications** - How these concepts apply in real-world scenarios\n3. **Practice Problems** - Working through examples to solidify your understanding\n\nWould you like me to elaborate on any of these areas?`,
          timestamp: new Date(),
        },
      ])
    }
  }

  const handleSendMessage = (content: string) => {
    const newUserMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content,
      timestamp: new Date(),
    }
    
    setMessages(prev => [...prev, newUserMessage])
    
    // Simulate AI response
    setTimeout(() => {
      const aiResponse: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `That's a great question! Let me help you understand this better.\n\nBased on what you're asking about, here are the key points:\n\n• **First**, it's important to grasp the foundational concept\n• **Second**, understanding how it connects to what you've learned before\n• **Third**, practicing with examples will help solidify your knowledge\n\nWould you like me to go deeper into any of these aspects, or would you prefer some practice problems?`,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, aiResponse])
    }, 1000)

    // Create new conversation if none exists
    if (!activeConversationId) {
      const newConversation: Conversation = {
        id: Date.now().toString(),
        title: content.slice(0, 30) + (content.length > 30 ? "..." : ""),
        date: "Today",
        preview: content,
      }
      setConversations(prev => [newConversation, ...prev])
      setActiveConversationId(newConversation.id)
    }
  }

  return (
    <div className="flex h-screen bg-background">
      <ConversationSidebar
        conversations={conversations}
        activeId={activeConversationId}
        onSelect={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onLogout={onLogout}
      />
      <ChatInterface
        messages={messages}
        onSendMessage={handleSendMessage}
      />
      <StreakCalendar />
    </div>
  )
}
