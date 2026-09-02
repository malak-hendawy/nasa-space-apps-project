import pandas as pd


def _translate(text_en: str, language: str) -> str:
	l = (language or "English").lower()
	translations = {
		"Data unavailable": {"arabic": "البيانات غير متوفرة", "spanish": "Datos no disponibles", "french": "Données indisponibles"},
		"No precipitation data available": {"arabic": "لا توجد بيانات هطول أمطار متاحة", "spanish": "No hay datos de precipitación disponibles", "french": "Aucune donnée de précipitation disponible"},
		"Heavy rain expected - carry umbrella": {"arabic": "أمطار غزيرة متوقعة - احمل مظلة", "spanish": "Lluvia intensa esperada - lleva paraguas", "french": "Pluie intense attendue - prenez un parapluie"},
		"Moderate rain chance - prepare for wet weather": {"arabic": "احتمال أمطار معتدلة - استعد للطقس الرطب", "spanish": "Probabilidad de lluvia moderada - prepárate para clima húmedo", "french": "Probabilité de pluie modérée - préparez-vous au temps humide"},
		"Light rain possible - keep umbrella handy": {"arabic": "أمطار خفيفة محتملة - احتفظ بمظلة قريبة", "spanish": "Posible lluvia ligera - mantén paraguas a mano", "french": "Pluie légère possible - gardez parapluie à portée"},
		"Very light rain possible": {"arabic": "أمطار خفيفة جداً محتملة", "spanish": "Posible lluvia muy ligera", "french": "Très légère pluie possible"},
		"Low rain risk": {"arabic": "مخاطر أمطار منخفضة", "spanish": "Riesgo bajo de lluvia", "french": "Faible risque de pluie"},
		"Extreme heat warning - avoid outdoor activities": {"arabic": "تحذير من حرارة شديدة - تجنب الأنشطة الخارجية", "spanish": "Advertencia de calor extremo - evita actividades al aire libre", "french": "Avertissement de chaleur extrême - évitez les activités extérieures"},
		"Very hot weather - stay hydrated and seek shade": {"arabic": "طقس حار جداً - اشرب الماء وابحث عن الظل", "spanish": "Clima muy caliente - mantente hidratado y busca sombra", "french": "Temps très chaud - restez hydraté et cherchez l'ombre"},
		"Hot weather - drink plenty of water": {"arabic": "طقس حار - اشرب الكثير من الماء", "spanish": "Clima caliente - bebe mucha agua", "french": "Temps chaud - buvez beaucoup d'eau"},
		"Cold weather - dress warmly": {"arabic": "طقس بارد - ارتدِ ملابس دافئة", "spanish": "Clima frío - vístete abrigado", "french": "Temps froid - habillez-vous chaudement"},
		"Consider irrigation - low rainfall": {"arabic": "فكر في الري - هطول أمطار منخفض", "spanish": "Considera riego - baja precipitación", "french": "Envisagez l'irrigation - faible précipitation"},
		"Delay irrigation - heavy rainfall expected": {"arabic": "أجل الري - أمطار غزيرة متوقعة", "spanish": "Retrasa riego - lluvia intensa esperada", "french": "Retardez l'irrigation - pluie intense attendue"},
		"Strong winds expected - secure outdoor items": {"arabic": "رياح قوية متوقعة - ثبت الأشياء الخارجية", "spanish": "Vientos fuertes esperados - asegura objetos exteriores", "french": "Vents forts attendus - sécurisez les objets extérieurs"},
		"Moderate winds - good for outdoor activities": {"arabic": "رياح معتدلة - جيدة للأنشطة الخارجية", "spanish": "Vientos moderados - buenos para actividades al aire libre", "french": "Vents modérés - bons pour les activités extérieures"},
		"Consider irrigation": {"arabic": "فكّر في الري", "spanish": "Considere el riego", "french": "Envisagez l'irrigation"},
		"Chance of rain: check the precipitation chart. Carry an umbrella if daily values exceed 10 mm.": {
			"arabic": "احتمال هطول المطر: راجع مخطط الهطول. احمل مظلة إذا تجاوزت القيم 10 مم يوميًا.",
			"spanish": "Probabilidad de lluvia: revisa la gráfica de precipitación. Lleva paraguas si supera 10 mm al día.",
			"french": "Risque de pluie: consultez le graphique des précipitations. Prenez un parapluie si > 10 mm/jour.",
		},
		"High temperatures: avoid peak afternoon, drink water, and plan shade.": {
			"arabic": "درجات حرارة مرتفعة: تجنب فترة الظهيرة، اشرب الماء، وخطط للظل.",
			"spanish": "Altas temperaturas: evita la tarde, bebe agua y busca sombra.",
			"french": "Températures élevées: évitez l'après-midi, buvez de l'eau et prévoyez de l'ombre.",
		},
		"For farming: if last 3-day average rain < 2 mm/day, schedule irrigation.": {
			"arabic": "للزراعة: إذا كان متوسط المطر لآخر 3 أيام أقل من 2 مم/يوم، خطط للري.",
			"spanish": "Para agricultura: si el promedio de 3 días < 2 mm/día, programe riego.",
			"french": "Agriculture: si la moyenne sur 3 jours < 2 mm/j, planifiez l'irrigation.",
		},
		"I can explain the charts, risks, and actions. Ask about rain, heat, or farming.": {
			"arabic": "يمكنني شرح المخططات والمخاطر والإجراءات. اسأل عن المطر أو الحرارة أو الزراعة.",
			"spanish": "Puedo explicar las gráficas, riesgos y acciones. Pregunta por lluvia, calor o agricultura.",
			"french": "Je peux expliquer les graphiques, les risques et les actions. Demandez pluie, chaleur ou agriculture.",
		},
	}
	if l == "english":
		return text_en
	return translations.get(text_en, {}).get(l, text_en)


def generate_advice(df: pd.DataFrame, language: str = "English") -> str:
	if df is None or df.empty:
		return _translate("Data unavailable", language)
	
	# Column names may be POWER codes or friendly names
	precip_col = "PRECTOT" if "PRECTOT" in df.columns else ("Precipitation" if "Precipitation" in df.columns else None)
	temp_col = "T2M" if "T2M" in df.columns else ("Temperature" if "Temperature" in df.columns else None)
	
	if not precip_col:
		return _translate("No precipitation data available", language)
		
	# Get recent data (last 3 days) and weekly data
	recent = df.tail(3)
	week = df.tail(7)
	
	# Calculate statistics
	avg_precip = recent[precip_col].mean(skipna=True) if precip_col else None
	max_precip = recent[precip_col].max(skipna=True) if precip_col else None
	min_precip = recent[precip_col].min(skipna=True) if precip_col else None
	
	avg_temp = week[temp_col].mean(skipna=True) if temp_col else None
	max_temp = week[temp_col].max(skipna=True) if temp_col else None
	min_temp = week[temp_col].min(skipna=True) if temp_col else None
	
	advices = []
	
	# Enhanced rain prediction logic
	if max_precip is not None and max_precip >= 10:  # Heavy rain
		advices.append(_translate("Heavy rain expected - carry umbrella", language))
	elif max_precip is not None and max_precip >= 5:  # Moderate rain
		advices.append(_translate("Moderate rain chance - prepare for wet weather", language))
	elif avg_precip is not None and avg_precip >= 2:  # Light rain
		advices.append(_translate("Light rain possible - keep umbrella handy", language))
	elif avg_precip is not None and avg_precip > 0:  # Very light rain
		advices.append(_translate("Very light rain possible", language))
	else:
		advices.append(_translate("Low rain risk", language))
	
	# Enhanced temperature advice
	if max_temp is not None and max_temp >= 40:  # Extreme heat
		advices.append(_translate("Extreme heat warning - avoid outdoor activities", language))
	elif max_temp is not None and max_temp >= 35:  # Very hot
		advices.append(_translate("Very hot weather - stay hydrated and seek shade", language))
	elif max_temp is not None and max_temp >= 30:  # Hot
		advices.append(_translate("Hot weather - drink plenty of water", language))
	elif min_temp is not None and min_temp <= 5:  # Cold
		advices.append(_translate("Cold weather - dress warmly", language))
	
	# Agricultural advice
	if avg_precip is not None and avg_precip < 1:
		advices.append(_translate("Consider irrigation - low rainfall", language))
	elif avg_precip is not None and avg_precip >= 15:
		advices.append(_translate("Delay irrigation - heavy rainfall expected", language))
	
	# Wind advice (if available)
	if "Windspeed" in df.columns:
		avg_wind = week["Windspeed"].mean(skipna=True)
		if avg_wind is not None and avg_wind >= 10:
			advices.append(_translate("Strong winds expected - secure outdoor items", language))
		elif avg_wind is not None and avg_wind >= 5:
			advices.append(_translate("Moderate winds - good for outdoor activities", language))
	
	return " • ".join(advices)


def chat_response(prompt: str, language: str = "English") -> str:
	text = (prompt or "").lower()
	if any(k in text for k in ["umbrella", "rain", "precip"]):
		return _translate("Chance of rain: check the precipitation chart. Carry an umbrella if daily values exceed 10 mm.", language)
	if any(k in text for k in ["heat", "hot", "temperature"]):
		return _translate("High temperatures: avoid peak afternoon, drink water, and plan shade.", language)
	if any(k in text for k in ["irrigation", "farm", "crop", "soil"]):
		return _translate("For farming: if last 3-day average rain < 2 mm/day, schedule irrigation.", language)
	return _translate("I can explain the charts, risks, and actions. Ask about rain, heat, or farming.", language)


