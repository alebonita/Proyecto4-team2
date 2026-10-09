@SPEC-EDGE-001
Feature: Capturas Edge

  Como página del celular que clasifica fotos con el modelo optimizado
  quiero enviar cada foto con su evento
  para que queden guardados en AWS sin duplicados.

  Scenario: Guardar una captura nueva
    Given una foto JPEG y un evento válido con capture_id "cap-0001"
    When se envía a POST /edge-captures
    Then la respuesta es 201 con el registro
    And la foto queda en S3 como "edge-captures/cap-0001.jpg"
    And existe un registro de "cap-0001" en la base de datos

  Scenario: Reenviar el mismo capture_id
    Given una captura "cap-0001" ya registrada
    When se vuelve a enviar a POST /edge-captures
    Then la respuesta es 200 con el registro existente
    And no se crea otro registro ni otra foto

  Scenario: Rechazar una confianza fuera de rango
    Given un evento con confidence 1.5
    When se envía a POST /edge-captures
    Then la respuesta es 400
    And no se guarda nada

  Scenario: Rechazar una clase que el modelo no predice
    Given un evento con predicted_class "bird"
    When se envía a POST /edge-captures
    Then la respuesta es 400
    And no se guarda nada

  Scenario: Rechazar una foto que no es JPEG
    Given una foto PNG
    When se envía a POST /edge-captures
    Then la respuesta es 400
    And no se guarda nada

  Scenario: Permitir la página del celular por CORS
    Given la página del celular en un origen permitido
    When hace la preflight OPTIONS a /edge-captures
    Then la respuesta incluye Access-Control-Allow-Origin con ese origen
