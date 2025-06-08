<template>
  <div id="app" class="app-container">
    <!-- Notificações globais -->
    <Transition name="notification">
      <div v-if="store.hasNotifications" class="notifications-container">
        <div
          v-for="notification in store.notifications"
          :key="notification.timestamp"
          :class="['notification', `notification--${notification.type}`]"
          @click="store.removeNotification(notification.timestamp)"
        >
          <span class="notification__icon">
            {{ getNotificationIcon(notification.type) }}
          </span>
          <span class="notification__content">{{ notification.content }}</span>
          <button class="notification__close" @click.stop="store.removeNotification(notification.timestamp)">
            ×
          </button>
        </div>
      </div>
    </Transition>

    <!-- O Vue Router renderizará a view correspondente aqui -->
    <router-view v-slot="{ Component }">
      <Transition name="fade" mode="out-in">
        <component :is="Component" />
      </Transition>
    </router-view>
  </div>
</template>

<script setup lang="ts">
import { useAppStore } from '@/store/appStore'

// A store é usada aqui principalmente para as notificações globais.
const store = useAppStore()

// Utilitário para ícone de notificação, pode ser movido para um composable se crescer.
const getNotificationIcon = (type: string) => {
  switch (type) {
    case 'error': return '❌'
    case 'status': return 'ℹ️'
    case 'transcription': return '📝'
    case 'response': return '🤖'
    default: return 'ℹ️'
  }
}
</script>

<style scoped>
/* Estilos globais para o contêiner da aplicação e transições */
.app-container {
  height: 100vh;
  width: 100vw;
  background: #111827;
  color: #d1d5db;
}

/* Notificações */
.notifications-container {
  position: fixed;
  top: clamp(20px, 5vh, 40px);
  right: clamp(1rem, 4vw, 2rem);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 400px;
  width: calc(100% - 2rem);
}

.notification {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: clamp(0.75rem, 2vw, 1rem);
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  transition: all 0.3s ease;
  border-left: 5px solid #6b7280;
}

.notification:hover {
  transform: translateX(-5px);
  box-shadow: 0 6px 25px rgba(0, 0, 0, 0.25);
}

.notification--error {
  border-left-color: #dc2626;
  background: #fef2f2;
}

.notification--status {
  border-left-color: #2563eb;
  background: #eff6ff;
}

.notification--transcription {
  border-left-color: #7c3aed;
  background: #f5f3ff;
}

.notification--response {
  border-left-color: #10b981;
  background: #f0fdf4;
}

.notification__icon {
  font-size: clamp(1rem, 3vw, 1.2rem);
  flex-shrink: 0;
}

.notification__content {
  flex: 1;
  font-size: clamp(0.85rem, 2.5vw, 0.95rem);
  color: #374151;
  word-break: break-word;
}

.notification__close {
  background: none;
  border: none;
  font-size: clamp(1.1rem, 3vw, 1.4rem);
  color: #9ca3af;
  cursor: pointer;
  padding: 0;
  line-height: 1;
  opacity: 0.7;
  transition: opacity 0.2s;
}
.notification__close:hover {
  opacity: 1;
}


/* Transições */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.notification-enter-active, .notification-leave-active {
  transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
}
.notification-enter-from, .notification-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
