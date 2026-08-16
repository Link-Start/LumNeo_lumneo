// frontend/src/api/models.ts

import { ModelConfig } from '@/stores/config'

const API_BASE = '/api/models'

export async function getModels(): Promise<ModelConfig[]> {
  const res = await fetch(API_BASE)
  if (!res.ok) throw new Error('Failed to fetch models')
  return res.json()
}

export async function createModel(model: Omit<ModelConfig, 'id'>): Promise<ModelConfig> {
  const res = await fetch(API_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model),
  })
  if (!res.ok) throw new Error('Failed to create model')
  return res.json()
}

export async function updateModel(id: string, updates: Partial<Omit<ModelConfig, 'id'>>): Promise<void> {
  const res = await fetch(`${API_BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error('Failed to update model')
}

export async function deleteModel(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete model')
}