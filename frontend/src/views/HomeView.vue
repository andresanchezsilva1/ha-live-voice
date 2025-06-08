<template>
  <div class="home">
    <h1>Home Assistant Voice Control POC</h1>
    <p>Interface de controle por voz para Home Assistant usando Gemini Live API</p>
    
    <div class="status-section">
      <h2>Status do Sistema</h2>
      <div class="status-indicators">
        <div class="status-item">
          <span class="status-label">Backend:</span>
          <span class="status-value">{{ backendStatus }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">WebSocket:</span>
          <span class="status-value">{{ websocketStatus }}</span>
        </div>
      </div>
    </div>

    <div class="controls-section">
      <h2>Controles de Voz</h2>
      <button @click="toggleRecording" :disabled="!isConnected" class="record-button">
        {{ isRecording ? 'Parar Gravação' : 'Iniciar Gravação' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

// Estado reativo
const backendStatus = ref('Desconectado')
const websocketStatus = ref('Desconectado')
const isConnected = ref(false)
const isRecording = ref(false)

// Funções
const toggleRecording = () => {
  isRecording.value = !isRecording.value
  // TODO: Implementar lógica de gravação
}

const checkBackendStatus = async () => {
  try {
    const response = await fetch('http://localhost:8000/health')
    if (response.ok) {
      backendStatus.value = 'Conectado'
      isConnected.value = true
    }
  } catch (error) {
    backendStatus.value = 'Erro de conexão'
    isConnected.value = false
  }
}

// Lifecycle
onMounted(() => {
  checkBackendStatus()
})
</script>

<style scoped>
.home {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
}

h1 {
  color: #2c3e50;
  text-align: center;
  margin-bottom: 1rem;
}

p {
  text-align: center;
  color: #7f8c8d;
  margin-bottom: 2rem;
}

.status-section, .controls-section {
  background: #f8f9fa;
  padding: 1.5rem;
  border-radius: 8px;
  margin-bottom: 2rem;
}

.status-indicators {
  display: flex;
  gap: 2rem;
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.status-label {
  font-weight: bold;
  color: #34495e;
}

.status-value {
  padding: 0.5rem 1rem;
  border-radius: 4px;
  background: #ecf0f1;
  color: #2c3e50;
}

.record-button {
  background: #3498db;
  color: white;
  border: none;
  padding: 1rem 2rem;
  border-radius: 8px;
  font-size: 1.1rem;
  cursor: pointer;
  transition: background-color 0.3s;
}

.record-button:hover:not(:disabled) {
  background: #2980b9;
}

.record-button:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
}
</style> 