import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import ruCommon from './locales/ru.json';
import enCommon from './locales/en.json';
import esCommon from './locales/es.json';

// Extract namespaces from the flat structure
const namespaces = [
  'common',
  'sidebar',
  'dashboard',
  'oxrana',
  'sites',
  'cameras',
  'detectors',
  'actuators',
  'alarms',
  'notifiers',
  'system'
];

const createResources = (flatTranslations: any) => {
  const resources: any = {};
  namespaces.forEach(ns => {
    if (flatTranslations[ns]) {
      resources[ns] = flatTranslations[ns];
    }
  });
  return resources;
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: createResources(ruCommon),
      en: createResources(enCommon),
      es: createResources(esCommon),
    },
    fallbackLng: 'ru',
    debug: false,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
    defaultNS: 'common',
  });

export default i18n;